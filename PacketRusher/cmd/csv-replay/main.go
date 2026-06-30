package main

import (
	"encoding/csv"
	"flag"
	"fmt"
	"io"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"

	"my5G-RANTester/config"
	"my5G-RANTester/internal/common/tools"
	gnbCtx "my5G-RANTester/internal/control_test_engine/gnb/context"
	"my5G-RANTester/internal/control_test_engine/procedures"
	"my5G-RANTester/internal/control_test_engine/ue"
	ueCtx "my5G-RANTester/internal/control_test_engine/ue/context"

	log "github.com/sirupsen/logrus"
)

type ueJob struct {
	id          int
	imsi        string
	msin        string
	arrivalSec  float64
	lifespanSec float64
}

func extractMsin(imsi string) (string, error) {
	s := strings.TrimPrefix(imsi, "imsi-")
	if len(s) != 15 {
		return "", fmt.Errorf("unexpected IMSI length for %q (want 15 digits after prefix, got %d)", imsi, len(s))
	}
	return s[5:], nil
}

func loadCSV(path string, limit int) ([]ueJob, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()

	r := csv.NewReader(f)
	r.FieldsPerRecord = -1

	header, err := r.Read()
	if err != nil {
		return nil, fmt.Errorf("reading header: %w", err)
	}
	col := map[string]int{}
	for i, h := range header {
		col[strings.TrimSpace(h)] = i
	}
	for _, req := range []string{"arrival_time", "departure_time", "imsi"} {
		if _, ok := col[req]; !ok {
			return nil, fmt.Errorf("CSV missing required column %q", req)
		}
	}

	var jobs []ueJob
	for i := 0; len(jobs) < limit; i++ {
		rec, err := r.Read()
		if err == io.EOF {
			break
		}
		if err != nil {
			return nil, fmt.Errorf("reading row %d: %w", i+2, err)
		}

		arrival, err := strconv.ParseFloat(rec[col["arrival_time"]], 64)
		if err != nil {
			return nil, fmt.Errorf("row %d: invalid arrival_time: %w", i+2, err)
		}
		departure, err := strconv.ParseFloat(rec[col["departure_time"]], 64)
		if err != nil {
			return nil, fmt.Errorf("row %d: invalid departure_time: %w", i+2, err)
		}
		imsi := strings.TrimSpace(rec[col["imsi"]])
		msin, err := extractMsin(imsi)
		if err != nil {
			return nil, fmt.Errorf("row %d: %w", i+2, err)
		}

		lifespan := departure - arrival
		if lifespan < 0 {
			lifespan = -lifespan
		}

		jobs = append(jobs, ueJob{
			id:          len(jobs) + 1,
			imsi:        imsi,
			msin:        msin,
			arrivalSec:  arrival,
			lifespanSec: lifespan,
		})
	}
	return jobs, nil
}

func simulateUE(job ueJob, baseCfg config.Config, gnb *gnbCtx.GNBContext, t0 time.Time, ueWg *sync.WaitGroup, doneWg *sync.WaitGroup) {
	defer doneWg.Done()

	arriveAt := t0.Add(time.Duration(job.arrivalSec * float64(time.Second)))
	if d := time.Until(arriveAt); d > 0 {
		time.Sleep(d)
	}

	log.Infof("[CSV][%s] arriving (lifespan %.1fs)", job.imsi, job.lifespanSec)

	ueCfg := baseCfg
	ueCfg.Ue.Msin = job.msin
	ueCfg.Ue.TunnelMode = config.TunnelDisabled

	ueRx := make(chan procedures.UeTesterMessage)
	ueWg.Add(1)
	ueTx := ue.NewUE(ueCfg, job.id, ueRx, gnb.GetInboundChannel(), ueWg)

	ueRx <- procedures.UeTesterMessage{Type: procedures.Registration}

	registered := false
	deregTimer := time.NewTimer(time.Duration(job.lifespanSec * float64(time.Second)))
	defer deregTimer.Stop()
	terminated := false

	for {
		select {
		case msg, ok := <-ueTx:
			if !ok {
				log.Infof("[CSV][%s] scenario channel closed", job.imsi)
				return
			}
			switch msg.StateChange {
			case ueCtx.MM5G_REGISTERED:
				if !registered {
					log.Infof("[CSV][%s] REGISTERED → requesting PDU session", job.imsi)
					ueRx <- procedures.UeTesterMessage{Type: procedures.NewPDUSession}
					registered = true
				}
			case ueCtx.MM5G_NULL:
				log.Infof("[CSV][%s] released", job.imsi)
				return
			}
		case <-deregTimer.C:
			if !terminated {
				log.Infof("[CSV][%s] lifespan expired → Terminate", job.imsi)
				ueRx <- procedures.UeTesterMessage{Type: procedures.Terminate}
				terminated = true
			}
		}
	}
}

func main() {
	csvPath := flag.String("csv", "/home/dave/oai/newsetup/simulation/runner/extracted/dataset/1jour/extracted_data_first_1days.csv", "CSV file")
	limit := flag.Int("n", 174285, "Number of UEs to replay") 
	logLevel := flag.String("loglevel", "info", "trace|debug|info|warn|error")
	flag.Parse()

	switch strings.ToLower(*logLevel) {
	case "trace":
		log.SetLevel(log.TraceLevel)
	case "debug":
		log.SetLevel(log.DebugLevel)
	case "warn":
		log.SetLevel(log.WarnLevel)
	case "error":
		log.SetLevel(log.ErrorLevel)
	default:
		log.SetLevel(log.InfoLevel)
	}

	jobs, err := loadCSV(*csvPath, *limit)
	if err != nil {
		log.Fatalf("loading CSV: %v", err)
	}
	log.Infof("[CSV] Loaded %d UE jobs from %s", len(jobs), *csvPath)
	for _, j := range jobs {
		log.Infof("[CSV]   #%d %s arrival=%.2fs lifespan=%.2fs", j.id, j.imsi, j.arrivalSec, j.lifespanSec)
	}

	cfg := config.GetConfig()

	ueWg := &sync.WaitGroup{}
	gnbs := tools.CreateGnbs(1, cfg, ueWg)
	log.Info("[CSV] Waiting 1s for NG Setup...")
	time.Sleep(1 * time.Second)

	var gnb *gnbCtx.GNBContext
	for _, g := range gnbs {
		gnb = g
		break
	}
	if gnb == nil {
		log.Fatal("[CSV] gNB initialization failed")
	}

	t0 := time.Now()
	log.Infof("[CSV] Simulation start t0=%s", t0.Format(time.RFC3339Nano))

	doneWg := &sync.WaitGroup{}
	for _, job := range jobs {
		doneWg.Add(1)
		go simulateUE(job, cfg, gnb, t0, ueWg, doneWg)
	}

	doneWg.Wait()
	log.Info("[CSV] All UE scheduler goroutines finished; waiting for UE goroutines to drain")

	drained := make(chan struct{})
	go func() {
		ueWg.Wait()
		close(drained)
	}()
	select {
	case <-drained:
		log.Info("[CSV] All UE goroutines exited cleanly")
	case <-time.After(120 * time.Second):
		log.Warn("[CSV] Timed out waiting for UE goroutines to drain; exiting anyway")
	}
}
