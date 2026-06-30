package attack

import (
	"context"
	"time"
)

type Limiter struct {
	ticker *time.Ticker
}

func NewLimiter(ratePerSecond int) *Limiter {
	if ratePerSecond < 1 {
		ratePerSecond = 1
	}
	interval := time.Second / time.Duration(ratePerSecond)
	if interval <= 0 {
		interval = time.Nanosecond
	}
	return &Limiter{ticker: time.NewTicker(interval)}
}

func (l *Limiter) Stop() {
	if l != nil && l.ticker != nil {
		l.ticker.Stop()
	}
}

func (l *Limiter) Wait(ctx context.Context) bool {
	if l == nil || l.ticker == nil {
		return true
	}
	select {
	case <-ctx.Done():
		return false
	case <-l.ticker.C:
		return true
	}
}
