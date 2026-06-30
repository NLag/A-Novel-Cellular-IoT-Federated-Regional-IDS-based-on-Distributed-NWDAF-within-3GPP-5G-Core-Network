#!/usr/bin/env python3
"""
Serial Chain Graph Data Processing Pipeline

Constructs graphs with three-hop paths: Service → API → Protocol → Service

Graph Structure (per fullgraph.md):
- Service Nodes: 8 core 5G NFs (AMF, SMF, UPF, NRF, AUSF, UDM, UDR, gNB)
- API Nodes: 150 unique endpoints (authentication, session, subscription, etc.)
- Protocol Nodes: 4 protocols (HTTP/2, PFCP, NGAP, NAS)

Output: PyTorch Geometric dataset for anomaly detection
Optimized for multi-core processing and large RAM
"""

import pandas as pd
import numpy as np
import json
import gzip
import re
from pathlib import Path
from collections import defaultdict
import torch
from torch_geometric.data import Data
from multiprocessing import Pool, cpu_count
from functools import partial
import os

# Set optimal number of threads for numpy/pandas
os.environ['OMP_NUM_THREADS'] = str(cpu_count())
os.environ['MKL_NUM_THREADS'] = str(cpu_count())

# ============================================================================
# Configuration
# ============================================================================
# File paths - Using merged dataset (50 iterations)
# Override via environment variables for pod deployment
PROTOCOL_EVENTS_FILE = os.environ.get("PROTOCOL_EVENTS_FILE", "/home/dave/oai/newsetup/data/100ue1202/output/merged_datasets/protocol_events.csv")
NF_EVENTS_FILE = os.environ.get("NF_EVENTS_FILE", "/home/dave/oai/newsetup/data/100ue1202/output/merged_datasets/nf_events.csv")
PROMETHEUS_FILE = os.environ.get("PROMETHEUS_FILE", "/home/dave/oai/newsetup/data/100ue1202/output/merged_datasets/query_result_1m_99.csv")
OUTPUT_FILE = os.environ.get("OUTPUT_FILE", "/home/dave/oai/newsetup/data/100ue1202/output/merged_datasets/dataset_serial_chain_50iter.pt")

# Time window configuration
WINDOW_SIZE_SECONDS = 5

# Parallel processing configuration
# Limit workers to avoid file descriptor exhaustion with PyTorch tensors
NUM_WORKERS = min(16, max(1, cpu_count() // 8))  # Conservative: use 1/8 of cores, max 16

# ============================================================================
# Graph Structure Definition (from fullgraph.md)
# ============================================================================
# 8 Service Nodes (Core 5G NFs) - IDs 0-7
SERVICE_NODES = [
    'AMF',   # 0 - Access and Mobility Management Function
    'SMF',   # 1 - Session Management Function
    'UPF',   # 2 - User Plane Function
    'NRF',   # 3 - Network Repository Function
    'AUSF',  # 4 - Authentication Server Function
    'UDM',   # 5 - Unified Data Management
    'UDR',   # 6 - Unified Data Repository
    'gNB',   # 7 - gNodeB (UERANSIM simulated - no Prometheus/NF events)
]

# Services that have Prometheus metrics (excludes UERANSIM gNB)
SERVICES_WITH_PROMETHEUS = ['AMF', 'SMF', 'UPF', 'NRF', 'AUSF', 'UDM', 'UDR']

# Services that generate NF events
SERVICES_WITH_NF_EVENTS = ['AMF', 'SMF']

# NF Event types per service (from nf_events.csv)
# AMF: CONNECTIVITY_STATE_REPORT, LOCATION_REPORT, REGISTRATION_STATE_REPORT
# SMF: PDU_SES_EST
NF_EVENT_TYPES = {
    'AMF': ['LOCATION_REPORT', 'REGISTRATION_STATE_REPORT', 'CONNECTIVITY_STATE_REPORT'],
    'SMF': ['PDU_SES_EST'],
}

# All possible NF event types for feature vector
ALL_NF_EVENT_TYPES = [
    'LOCATION_REPORT',
    'REGISTRATION_STATE_REPORT', 
    'CONNECTIVITY_STATE_REPORT',
    'PDU_SES_EST',
]

# State values to track (extracted from event data JSON)
REGISTRATION_STATES = ['REGISTERED', 'DEREGISTERED']
CONNECTIVITY_STATES = ['CONNECTED', 'IDLE']

# Mapping from pod names to canonical service names
SERVICE_NAME_MAPPING = {
    'oai-amf': 'AMF', 'amf': 'AMF',
    'oai-smf': 'SMF', 'smf': 'SMF',
    'oai-upf': 'UPF', 'upf': 'UPF',
    'oai-nrf': 'NRF', 'nrf': 'NRF',
    'oai-ausf': 'AUSF', 'ausf': 'AUSF',
    'oai-udm': 'UDM', 'udm': 'UDM',
    'oai-udr': 'UDR', 'udr': 'UDR',
    'oai-gnb': 'gNB', 'gnb': 'gNB', 'nr-gnb': 'gNB', 'oai-nr-ue': 'gNB',
}

# API Endpoint Nodes - IDs 8 onwards (from top_apis.csv)
# Updated to match actual data - 150 most frequent endpoints
API_NODES = [
    # Top notification APIs
    '/dccf/amf-notifications',
    '/dccf/smf-notifications',
    
    # Authentication & Security APIs
    '/nudr-dr/v1/subscription-data/{id}/authentication-data/authentication-subscription',
    '/nausf-auth/v1/ue-authentications',
    '/nudm-ueau/v1/{id}/auth-events',
    '/nudm-ueau/v1/{id}/security-information/generate-auth-data',
    '/nudr-dr/v1/subscription-data/{id}/authentication-data/authentication-status',
    '/nausf-auth/v1/ue-authentications/{id}/{id}g-aka-confirmation',
    
    # Subscription Data APIs
    '/nudm-sdm/v1/{id}/nssai',
    '/nudr-dr/v1/subscription-data/{id}/{id}/provisioned-data/am-data',
    '/nnrf-disc/v1/nf-instances',
    
    # Session Management APIs
    '/nsmf-pdusession/v1/sm-contexts/{id}/modify',
    '/nsmf-pdusession/v1/sm-contexts',
    '/nsmf-pdusession/v1/sm-contexts/{id}/release',
    
    # NGAP Messages
    'NGAP:id-UplinkNASTransport',
    'NGAP:id-DownlinkNASTransport',
    'NGAP:id-InitialContextSetup',
    'NGAP:id-PDUSessionResourceSetup',
    'NGAP:id-UEContextRelease',
    'NGAP:id-InitialUEMessage',
    
    # PFCP Messages
    'PFCP:SessionEstablishmentRequest',
    'PFCP:SessionEstablishmentResponse',
    'PFCP:SessionModificationResponse',
    'PFCP:SessionModificationRequest',
    'PFCP:SessionDeletionRequest',
    'PFCP:SessionDeletionResponse',
    'PFCP:HeartbeatResponse',
    'PFCP:HeartbeatRequest',
    
    # NAS Messages
    'NAS:Registration request',
    'NAS:Authentication response',
    'NAS:Authentication request',
    'NAS:Security mode command',
    'NAS:Registration accept',
    'NAS:Security mode complete',
    'NAS:DL NAS transport',
    'NAS:Registration complete',
    'NAS:UL NAS transport',
    'NAS:MO Deregistration request',
    'NAS:MO Deregistration accept',
    
    # NF Management APIs
    '/nnrf-nfm/v1/nf-instances/{id}-0267-4e6f-84d3-4ed61671dc6f',
    '/nnrf-nfm/v1/nf-instances/{id}-ddd1-4729-b39c-7bad403d1282',
    '/nnrf-nfm/v1/nf-instances/{id}-0ba6-4662-a29a-188dbcd83302',
    '/nnrf-nfm/v1/nf-instances/{id}-35c7-4c6e-bef9-fdaeb2c8b1ff',
    '/nnrf-nfm/v1/nf-instances/{id}-4586-4f38-8f1f-8c8c0a1c3c7e',
    '/nnrf-nfm/v1/nf-instances/{id}-3501-407e-b565-16c38b50e008',
    '/nnrf-nfm/v1/nf-instances/{id}-a1ab-49fa-8b8d-4ba3e323043a',
    
    # AMF Communication API (aggregated per-UE endpoint)
    '/namf-comm/v1/ue-contexts/imsi-{imsi}/n1-n2-messages',
]

# 4 Protocol Nodes - IDs after API nodes
PROTOCOL_NODES = [
    'HTTP/2',  # Service-Based Architecture protocol
    'PFCP',    # Packet Forwarding Control Protocol
    'NGAP',    # NG Application Protocol
    'NAS',     # Non-Access Stratum
]

# Total: 8 service + 46 API + 4 protocol = 58 nodes (per-UE endpoints aggregated)

# ============================================================================
# Prometheus Metric Patterns (from querydef.py)
# ============================================================================
# Metric name patterns in the Prometheus CSV columns
# Column format: {"__name__":"metric_name","label1":"value1",...}
PROMETHEUS_METRIC_PATTERNS = {
    # Response time metrics (latency)
    'latency': [
        'response_time_ms_99th_percentile',
        'response_time_ms_95th_percentile', 
        'response_time_ms_90th_percentile',
        'recorded_response_time_99th_percentile',
    ],
    # Request rate metrics
    'request_rate': [
        'requests_rate_1m',
        'requests_rate_2m',
        'requests_rate_5m',
        'registration_requests_rate',
    ],
    # Error rate metrics
    'error_rate': [
        'responses_error_rate_1m',
        'responses_error_rate_2m',
        'responses_error_rate_5m',
        'registrations_error_rate',
    ],
    # CPU metrics
    'cpu': [
        'cpu_consumption_1m',
        'cpu_consumption_percent_1m',
        'cpu_consumption_2m',
        'cpu_consumption_5m',
    ],
    # Memory metrics
    'memory': [
        'memory_consumption_1m',
        'memory_consumption_mb',
        'memory_consumption_2m',
        'memory_consumption_5m',
    ],
    # Registration time
    'registration_time': [
        'registration_time_ms_99th_percentile',
        'registration_time_ms_95th_percentile',
        'recorded_registration_time_99th_percentile',
    ],
}

# Service name variations in Prometheus labels
SERVICE_LABEL_VARIATIONS = {
    'AMF': ['oai-amf', 'amf'],
    'SMF': ['oai-smf', 'smf'],
    'UPF': ['oai-upf', 'upf'],
    'NRF': ['oai-nrf', 'nrf'],
    'AUSF': ['oai-ausf', 'ausf'],
    'UDM': ['oai-udm', 'udm'],
    'UDR': ['oai-udr', 'udr'],
    'gNB': ['gnb', 'nr-gnb', 'oai-gnb'],
}

# ============================================================================
# API Extraction Functions
# ============================================================================
def parse_metadata_safe(metadata_str):
    """Safely parse metadata JSON"""
    if pd.isna(metadata_str):
        return None
    try:
        if isinstance(metadata_str, str):
            return json.loads(metadata_str)
        return metadata_str
    except:
        return None


def extract_api_from_http2(metadata):
    """Extract API endpoint from HTTP/2 metadata"""
    if not metadata:
        return None

    path = metadata.get('path') or metadata.get('url') or metadata.get(':path')
    if path:
        return normalize_api_path(path)

    return None


def extract_api_from_pfcp(metadata):
    """Extract operation from PFCP metadata"""
    if not metadata:
        return None

    msg_type = metadata.get('message_type') or metadata.get('type')
    if msg_type:
        return f"PFCP:{msg_type}"

    return None


def extract_api_from_ngap(metadata):
    """Extract procedure from NGAP metadata"""
    if not metadata:
        return None

    procedure = metadata.get('procedure') or metadata.get('message_type')
    if procedure:
        return f"NGAP:{procedure}"

    return None


def extract_api_from_nas(metadata):
    """Extract message type from NAS metadata"""
    if not metadata:
        return None

    msg_type = metadata.get('message_type') or metadata.get('procedure')
    if msg_type:
        return f"NAS:{msg_type}"

    return None


def extract_api_endpoint(protocol, metadata_str):
    """Extract API endpoint based on protocol type"""
    metadata = parse_metadata_safe(metadata_str)

    if not metadata:
        return None

    protocol_lower = protocol.lower() if isinstance(protocol, str) else ""

    if 'http' in protocol_lower:
        return extract_api_from_http2(metadata)
    elif 'pfcp' in protocol_lower:
        return extract_api_from_pfcp(metadata)
    elif 'ngap' in protocol_lower:
        return extract_api_from_ngap(metadata)
    elif 'nas' in protocol_lower:
        return extract_api_from_nas(metadata)

    return None


def get_protocol_node_name(protocol_str):
    """Map protocol string to canonical protocol node name"""
    if not protocol_str:
        return None
    
    protocol_lower = protocol_str.lower()
    
    if 'http' in protocol_lower:
        return 'HTTP/2'
    elif 'pfcp' in protocol_lower:
        return 'PFCP'
    elif 'ngap' in protocol_lower:
        return 'NGAP'
    elif 'nas' in protocol_lower:
        return 'NAS'
    
    return None


# ============================================================================
# Data Loading Functions (Optimized)
# ============================================================================
def load_prometheus_data(file_path):
    """Load Prometheus metrics with optimized dtypes"""
    print(f"Loading Prometheus data from {file_path}...")
    
    # Read with optimal dtypes
    df = pd.read_csv(file_path, 
                     dtype={'timestamp': np.int64},
                     low_memory=False)
    
    # Convert metric columns to float32 (saves 50% memory vs float64)
    for col in df.columns:
        if col != 'timestamp' and df[col].dtype == np.float64:
            df[col] = df[col].astype(np.float32)
    
    print(f"Loaded {len(df)} Prometheus samples")
    print(f"Memory usage: {df.memory_usage(deep=True).sum() / 1024**2:.1f} MB")
    return df


def load_protocol_events(file_path):
    """Load protocol events with optimized dtypes and minimal processing"""
    print(f"Loading protocol events from {file_path}...")
    
    # Read with optimal dtypes
    dtype_spec = {
        'protocol': 'category',
        'event_type': 'category',
    }
    
    df = pd.read_csv(file_path, dtype=dtype_spec, low_memory=False)
    
    # Convert timestamp to int64, handling NaN and floats
    if 'timestamp' in df.columns:
        df['timestamp'] = pd.to_numeric(df['timestamp'], errors='coerce').fillna(0).astype(np.int64)
    
    # Convert to category to save memory
    if 'src_pod_name' in df.columns:
        df['src_pod_name'] = df['src_pod_name'].astype('category')
    if 'dst_pod_name' in df.columns:
        df['dst_pod_name'] = df['dst_pod_name'].astype('category')

    # Extract API endpoints sequentially (more memory efficient)
    print("Extracting API endpoints from metadata...")
    print("  (Processing in batches to conserve memory)")
    
    batch_size = 100000
    api_endpoints = []
    
    for i in range(0, len(df), batch_size):
        end_idx = min(i + batch_size, len(df))
        batch = df.iloc[i:end_idx]
        batch_apis = batch.apply(
            lambda row: extract_api_endpoint(row['protocol'], row['metadata']),
            axis=1
        )
        api_endpoints.append(batch_apis)
        if (i // batch_size) % 5 == 0:
            print(f"  Processed {end_idx}/{len(df)} events...")
    
    df['api_endpoint'] = pd.concat(api_endpoints, ignore_index=True)

    print(f"Loaded {len(df)} protocol events")
    print(f"Events with API: {df['api_endpoint'].notna().sum()} ({df['api_endpoint'].notna().sum()/len(df)*100:.1f}%)")
    print(f"Memory usage: {df.memory_usage(deep=True).sum() / 1024**2:.1f} MB")

    return df


def extract_api_endpoints_chunk(chunk):
    """Extract API endpoints for a chunk of rows"""
    return chunk.apply(
        lambda row: extract_api_endpoint(row['protocol'], row['metadata']),
        axis=1
    )


def load_nf_events(file_path):
    """Load NF events with optimized dtypes"""
    print(f"Loading NF events from {file_path}...")
    
    dtype_spec = {
        'event_type': 'category',
        'source': 'category',
    }
    
    df = pd.read_csv(file_path, dtype=dtype_spec)
    
    # Convert timestamp to int64, handling NaN and floats
    if 'timestamp' in df.columns:
        df['timestamp'] = pd.to_numeric(df['timestamp'], errors='coerce').fillna(0).astype(np.int64)
    
    print(f"Loaded {len(df)} NF events")
    print(f"Memory usage: {df.memory_usage(deep=True).sum() / 1024**2:.1f} MB")
    return df


# ============================================================================
# Caching and Pre-computation
# ============================================================================
# Cache for parsed Prometheus columns (avoid re-parsing)
_prometheus_column_cache = {}

def parse_prometheus_column_cached(col_name):
    """Parse Prometheus column with caching"""
    if col_name in _prometheus_column_cache:
        return _prometheus_column_cache[col_name]
    
    result = parse_prometheus_column(col_name)
    _prometheus_column_cache[col_name] = result
    return result


# Pre-compile regex patterns
_uuid_pattern = re.compile(r'/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')
_imsi_pattern = re.compile(r'/imsi-\d+')
_supi_pattern = re.compile(r'/supi-\d+')
_numeric_pattern = re.compile(r'/(\d{6,})')
_pod_suffix_pattern = re.compile(r'-[a-z0-9]{8,}-[a-z0-9]{5,}$')


def normalize_api_path(path):
    """Normalize API paths to match fullgraph.md format (optimized)"""
    if not path:
        return path

    # Remove query parameters
    path = path.split('?')[0].rstrip('/')

    # Replace patterns using pre-compiled regex
    path = _uuid_pattern.sub('/{id}', path)
    
    # Aggregate IMSI-specific paths (e.g., /ue-contexts/imsi-001010000000001/... -> /ue-contexts/imsi-{imsi}/...)
    path = _imsi_pattern.sub('/imsi-{imsi}', path)
    
    path = _supi_pattern.sub('/{id}', path)
    path = _numeric_pattern.sub('/{id}', path)

    return path


def normalize_service_name(full_name):
    """Normalize pod name to canonical service name (optimized)"""
    if pd.isna(full_name):
        return None
    
    # Remove pod suffixes using pre-compiled pattern
    normalized = _pod_suffix_pattern.sub('', full_name.lower())
    
    # Map to canonical name
    return SERVICE_NAME_MAPPING.get(normalized, None)


# ============================================================================
# Feature Extraction Functions (Vectorized)
# ============================================================================
def extract_service_features_prometheus(prom_window, service_name):
    """
    Extract Prometheus metrics for a service from window (vectorized).
    
    Returns 20 features:
    - CPU: mean, max, min, std (4)
    - Memory: mean, max, min, std (4)
    - Request rate: mean, max, min, std (4)
    - Error rate: mean, max, min, std (4)
    - Latency: mean, max, min, std (4)
    """
    if service_name == 'gNB' or service_name not in SERVICES_WITH_PROMETHEUS:
        return np.zeros(20, dtype=np.float32)
    
    if len(prom_window) == 0:
        return np.zeros(20, dtype=np.float32)
    
    # Pre-filter relevant columns
    service_variations = SERVICE_LABEL_VARIATIONS.get(service_name, [service_name.lower()])
    
    # Collect values by metric category (vectorized where possible)
    metric_values = {
        'cpu': [],
        'memory': [],
        'request_rate': [],
        'error_rate': [],
        'latency': [],
    }
    
    for col in prom_window.columns:
        if col == 'timestamp':
            continue
        
        # Use cached parsing
        label_dict = parse_prometheus_column_cached(col)
        
        if label_dict is None:
            continue
        
        # Quick service match check
        matched = False
        for field in ['deployment_name', 'client_deployment_name', 'server_deployment_name', 
                     'pod', 'container', 'service', 'job']:
            if field in label_dict:
                label_value = label_dict[field].lower()
                for variation in service_variations:
                    if variation.lower() in label_value:
                        matched = True
                        break
                if matched:
                    break
        
        if not matched:
            continue
        
        # Get the metric name and category
        metric_name = label_dict.get('__name__', '')
        category = get_metric_category(metric_name)
        
        if category in ['cpu', 'memory', 'request_rate', 'error_rate', 'latency', 'registration_time']:
            # Get values as numpy array directly
            values = prom_window[col].values
            values = values[~np.isnan(values)]
            
            if len(values) > 0:
                if category == 'registration_time':
                    metric_values['latency'].extend(values.tolist())
                else:
                    metric_values[category].extend(values.tolist())
    
    # Vectorized statistics computation
    def compute_stats_vectorized(values):
        """Compute [mean, max, min, std] vectorized"""
        if not values:
            return np.zeros(4, dtype=np.float32)
        arr = np.array(values, dtype=np.float32)
        arr = arr[np.isfinite(arr)]
        if len(arr) == 0:
            return np.zeros(4, dtype=np.float32)
        return np.array([
            np.mean(arr),
            np.max(arr),
            np.min(arr),
            np.std(arr) if len(arr) > 1 else 0.0
        ], dtype=np.float32)
    
    # Build feature vector
    features = np.concatenate([
        compute_stats_vectorized(metric_values['cpu']),
        compute_stats_vectorized(metric_values['memory']),
        compute_stats_vectorized(metric_values['request_rate']),
        compute_stats_vectorized(metric_values['error_rate']),
        compute_stats_vectorized(metric_values['latency']),
    ])
    
    return features


def extract_service_features_protocol(window_df, service_name):
    """Extract protocol event features for a service node"""
    if len(window_df) == 0:
        return np.zeros(16)
    
    # Events where service is source or destination
    src_events = window_df[window_df['src_normalized'] == service_name]
    dst_events = window_df[window_df['dst_normalized'] == service_name]
    all_service_events = pd.concat([src_events, dst_events]).drop_duplicates()

    features = []
    
    # 1. Protocol counts as source/destination (8 features)
    for proto in PROTOCOL_NODES:
        src_count = len(src_events[src_events['protocol_node'] == proto])
        dst_count = len(dst_events[dst_events['protocol_node'] == proto])
        features.extend([float(src_count), float(dst_count)])
    
    # 2. Request vs Response counts (2 features)
    request_count = len(all_service_events[all_service_events['event_type'] == 'request'])
    response_count = len(all_service_events[all_service_events['event_type'] == 'response'])
    features.extend([float(request_count), float(response_count)])
    
    # 3. Response time statistics from metadata (4 features)
    response_times = []
    for _, row in all_service_events.iterrows():
        metadata = parse_metadata_safe(row.get('metadata', '{}'))
        if metadata and 'response_time' in metadata:
            try:
                rt = float(metadata['response_time'])
                response_times.append(rt)
            except:
                pass
    
    if response_times:
        features.extend([
            float(np.mean(response_times)),
            float(np.max(response_times)),
            float(np.min(response_times)),
            float(np.std(response_times)) if len(response_times) > 1 else 0.0
        ])
    else:
        features.extend([0.0, 0.0, 0.0, 0.0])
    
    # 4. Unique communication partners (2 features)
    unique_src_partners = src_events['dst_normalized'].nunique()
    unique_dst_partners = dst_events['src_normalized'].nunique()
    features.extend([float(unique_src_partners), float(unique_dst_partners)])

    return np.array(features[:16], dtype=np.float32)


def extract_service_features_nf(nf_window, service_name):
    """Extract NF event features for a service node"""
    # Only AMF and SMF generate NF events
    if service_name not in SERVICES_WITH_NF_EVENTS:
        return np.zeros(12)
    
    if len(nf_window) == 0:
        return np.zeros(12)
    
    features = []
    
    # Filter events for this service (check 'source' column)
    if 'source' in nf_window.columns:
        service_events = nf_window[nf_window['source'].str.upper() == service_name.upper()]
    else:
        service_events = pd.DataFrame()
    
    # 1. Event type counts (4 features)
    for event_type in ALL_NF_EVENT_TYPES:
        if len(service_events) > 0 and 'event_type' in service_events.columns:
            count = len(service_events[service_events['event_type'] == event_type])
        else:
            count = 0
        features.append(float(count))
    
    # 2. State counts from event data (4 features)
    registered_count = 0
    deregistered_count = 0
    connected_count = 0
    idle_count = 0
    unique_supis = set()
    
    if len(service_events) > 0 and 'data' in service_events.columns:
        for _, row in service_events.iterrows():
            event_data = parse_metadata_safe(row.get('data', '{}'))
            if event_data:
                # Track unique subscribers
                supi = event_data.get('supi', '')
                if supi:
                    unique_supis.add(supi)
                
                # Check rmInfoList for registration state
                rm_info_list = event_data.get('rmInfoList', [])
                for rm_info in rm_info_list:
                    rm_state = rm_info.get('rmState', '')
                    if rm_state == 'REGISTERED':
                        registered_count += 1
                    elif rm_state == 'DEREGISTERED':
                        deregistered_count += 1
                
                # Check cmInfoList for connectivity state
                cm_info_list = event_data.get('cmInfoList', [])
                for cm_info in cm_info_list:
                    cm_state = cm_info.get('cmState', '')
                    if cm_state == 'CONNECTED':
                        connected_count += 1
                    elif cm_state == 'IDLE':
                        idle_count += 1
    
    features.extend([
        float(registered_count),
        float(deregistered_count),
        float(connected_count),
        float(idle_count)
    ])
    
    # 3. Aggregate statistics (4 features)
    features.append(float(len(service_events)))  # Total events
    features.append(float(service_events['event_type'].nunique()) if len(service_events) > 0 and 'event_type' in service_events.columns else 0.0)
    features.append(float(len(unique_supis)))  # Unique subscribers
    features.append(0.0)  # Placeholder
    
    return np.array(features[:12], dtype=np.float32)


def extract_api_features(window_df, api_endpoint, api_to_id):
    """Extract features for an API node"""
    if len(window_df) == 0:
        return np.zeros(16)
    
    # Find all events matching this API
    matching_events = window_df[window_df['matched_api'] == api_endpoint]

    if len(matching_events) == 0:
        return np.zeros(16)

    features = []
    
    # 1. Basic counts (4 features)
    features.append(float(len(matching_events)))  # Request count
    features.append(float(matching_events['protocol'].nunique()))  # Number of protocols
    features.append(float(matching_events['src_normalized'].nunique()))  # Unique sources
    features.append(float(matching_events['dst_normalized'].nunique()))  # Unique destinations
    
    # 2. Request/Response breakdown (2 features)
    request_count = len(matching_events[matching_events['event_type'] == 'request'])
    response_count = len(matching_events[matching_events['event_type'] == 'response'])
    features.extend([float(request_count), float(response_count)])
    
    # 3. Response time statistics (4 features)
    response_times = []
    for _, row in matching_events.iterrows():
        metadata = parse_metadata_safe(row.get('metadata', '{}'))
        if metadata and 'response_time' in metadata:
            try:
                rt = float(metadata['response_time'])
                response_times.append(rt)
            except:
                pass
    
    if response_times:
        features.extend([
            float(np.mean(response_times)),
            float(np.max(response_times)),
            float(np.min(response_times)),
            float(np.std(response_times)) if len(response_times) > 1 else 0.0
        ])
    else:
        features.extend([0.0, 0.0, 0.0, 0.0])
    
    # 4. HTTP-specific features (4 features)
    method_counts = {'get': 0, 'post': 0, 'patch': 0, 'put': 0, 'delete': 0}
    for _, row in matching_events.iterrows():
        metadata = parse_metadata_safe(row.get('metadata', '{}'))
        if metadata:
            method = metadata.get('method', '').lower()
            if method in method_counts:
                method_counts[method] += 1
    
    features.extend([
        float(method_counts['get']),
        float(method_counts['post']),
        float(method_counts['patch'] + method_counts['put']),
        float(method_counts['delete'])
    ])
    
    # 5. Error tracking (2 features)
    error_count = 0
    success_count = 0
    for _, row in matching_events.iterrows():
        metadata = parse_metadata_safe(row.get('metadata', '{}'))
        if metadata:
            cause = metadata.get('cause', '')
            if cause and cause != 'none':
                error_count += 1
            elif row.get('event_type') == 'response':
                success_count += 1
    
    features.extend([float(error_count), float(success_count)])

    return np.array(features[:16], dtype=np.float32)


def extract_protocol_features(window_df, protocol):
    """Extract features for a protocol node"""
    if len(window_df) == 0:
        return np.zeros(16)
    
    protocol_name = get_protocol_node_name(protocol)
    if not protocol_name:
        return np.zeros(16)
    
    # Match by canonical protocol name
    proto_events = window_df[window_df['protocol_node'] == protocol_name]

    if len(proto_events) == 0:
        return np.zeros(16)

    features = []
    
    # 1. Basic counts (4 features)
    features.append(float(len(proto_events)))  # Total message count
    features.append(float(proto_events['matched_api'].nunique()))  # Unique APIs
    features.append(float(proto_events['src_normalized'].nunique()))  # Unique sources
    features.append(float(proto_events['dst_normalized'].nunique()))  # Unique destinations
    
    # 2. Request/Response breakdown (2 features)
    request_count = len(proto_events[proto_events['event_type'] == 'request'])
    response_count = len(proto_events[proto_events['event_type'] == 'response'])
    features.extend([float(request_count), float(response_count)])
    
    # 3. Response time statistics (4 features)
    response_times = []
    for _, row in proto_events.iterrows():
        metadata = parse_metadata_safe(row.get('metadata', '{}'))
        if metadata and 'response_time' in metadata:
            try:
                rt = float(metadata['response_time'])
                response_times.append(rt)
            except:
                pass
    
    if response_times:
        features.extend([
            float(np.mean(response_times)),
            float(np.max(response_times)),
            float(np.min(response_times)),
            float(np.std(response_times)) if len(response_times) > 1 else 0.0
        ])
    else:
        features.extend([0.0, 0.0, 0.0, 0.0])
    
    # 4. Protocol-specific features (6 features)
    heartbeat_count = 0
    session_count = 0
    error_count = 0
    success_count = 0
    
    for _, row in proto_events.iterrows():
        metadata = parse_metadata_safe(row.get('metadata', '{}'))
        if metadata:
            msg_type = metadata.get('message_type', '')
            cause = metadata.get('cause', '')
            
            if 'Heartbeat' in msg_type:
                heartbeat_count += 1
            elif 'Session' in msg_type:
                session_count += 1
            
            if cause and cause != 'none':
                error_count += 1
            elif row.get('event_type') == 'response':
                success_count += 1
    
    features.extend([
        float(heartbeat_count),
        float(session_count),
        float(error_count),
        float(success_count),
        float(success_count / max(success_count + error_count, 1)),  # Success rate
        0.0  # Placeholder
    ])

    return np.array(features[:16], dtype=np.float32)


def extract_edge_features_prometheus(prom_window, src_service, dst_service):
    """
    Extract Prometheus metrics relevant to an edge (communication between services).
    Uses client_deployment_name/server_deployment_name labels for inter-service metrics.
    
    Returns 8 features:
    - Request rate: mean, max (2)
    - Error rate: mean, max (2)
    - Latency: mean, max, min, std (4)
    """
    if len(prom_window) == 0:
        return np.zeros(8)
    
    # gNB doesn't have Prometheus metrics
    if src_service == 'gNB' or dst_service == 'gNB':
        return np.zeros(8)
    
    src_variations = SERVICE_LABEL_VARIATIONS.get(src_service, [src_service.lower()])
    dst_variations = SERVICE_LABEL_VARIATIONS.get(dst_service, [dst_service.lower()])
    
    request_rate = []
    error_rate = []
    latency = []
    
    for col in prom_window.columns:
        if col == 'timestamp':
            continue
        
        label_dict = parse_prometheus_column_cached(col)
        if label_dict is None:
            continue
        
        # Check for client/server relationship
        client = label_dict.get('client_deployment_name', '').lower()
        server = label_dict.get('server_deployment_name', '').lower()
        
        # Match source as client and destination as server
        src_match = any(v.lower() in client for v in src_variations)
        dst_match = any(v.lower() in server for v in dst_variations)
        
        if not (src_match and dst_match):
            continue
        
        # Get metric category
        metric_name = label_dict.get('__name__', '')
        category = get_metric_category(metric_name)
        
        values = prom_window[col].dropna().values
        if len(values) == 0:
            continue
        
        values = values[np.isfinite(values)]
        if len(values) == 0:
            continue
        
        if category == 'request_rate':
            request_rate.extend(values.tolist())
        elif category == 'error_rate':
            error_rate.extend(values.tolist())
        elif category == 'latency':
            latency.extend(values.tolist())
    
    features = []
    
    # Request rate stats (2 features: mean, max)
    if request_rate:
        arr = np.array(request_rate)
        features.extend([float(np.mean(arr)), float(np.max(arr))])
    else:
        features.extend([0.0, 0.0])
    
    # Error rate stats (2 features: mean, max)
    if error_rate:
        arr = np.array(error_rate)
        features.extend([float(np.mean(arr)), float(np.max(arr))])
    else:
        features.extend([0.0, 0.0])
    
    # Latency stats (4 features: mean, max, min, std)
    if latency:
        arr = np.array(latency)
        features.extend([
            float(np.mean(arr)),
            float(np.max(arr)),
            float(np.min(arr)),
            float(np.std(arr)) if len(arr) > 1 else 0.0
        ])
    else:
        features.extend([0.0, 0.0, 0.0, 0.0])
    
    return np.array(features, dtype=np.float32)

def normalize_edge_features(edge_features):
    """Normalize edge features similar to node features"""
    if len(edge_features) == 0:
        return edge_features
    
    # Log transform counts (first 3 features: message, request, response counts)
    edge_features[:, :3] = np.log1p(edge_features[:, :3])
    
    # Log transform response times (features 3-4)
    edge_features[:, 3:5] = np.log1p(edge_features[:, 3:5])
    
    # Edge type (feature 5) is categorical, leave as-is
    
    # Normalize Prometheus metrics (features 6-13) - they can be very large
    for i in range(6, 14):
        col = edge_features[:, i]
        if col.max() > 10:
            edge_features[:, i] = np.log1p(col)
    
    return edge_features


def extract_edges_and_features(window_df, prom_window, service_to_id, api_to_id, protocol_to_id):
    """
    Extract edges for Serial Chain: Service → API → Protocol → Service
    Now includes Prometheus metrics as additional edge features.
    """
    edge_list = []
    edge_type_list = []
    edge_feature_list = []

    # Filter events with valid mappings
    valid_df = window_df[
        (window_df['matched_api'].notna()) &
        (window_df['src_normalized'].notna()) &
        (window_df['dst_normalized'].notna()) &
        (window_df['protocol_node'].notna()) &
        (window_df['src_normalized'].isin(service_to_id.keys())) &
        (window_df['dst_normalized'].isin(service_to_id.keys())) &
        (window_df['matched_api'].isin(api_to_id.keys())) &
        (window_df['protocol_node'].isin(protocol_to_id.keys()))
    ]

    # Group by complete paths
    grouped = valid_df.groupby(
        ['src_normalized', 'matched_api', 'protocol_node', 'dst_normalized'],
        observed=True
    )

    for (src_service, api, protocol, dst_service), group in grouped:
        message_count = len(group)
        
        # Extract edge-level features from the group
        request_count = len(group[group['event_type'] == 'request'])
        response_count = len(group[group['event_type'] == 'response'])
        
        # Response time statistics for this path
        response_times = []
        for _, row in group.iterrows():
            metadata = parse_metadata_safe(row.get('metadata', '{}'))
            if metadata and 'response_time' in metadata:
                try:
                    response_times.append(float(metadata['response_time']))
                except:
                    pass
        
        avg_response_time = np.mean(response_times) if response_times else 0.0
        max_response_time = np.max(response_times) if response_times else 0.0

        # Get Prometheus edge features for this service pair
        prom_edge_features = extract_edge_features_prometheus(prom_window, src_service, dst_service)

        # Get node IDs
        src_id = service_to_id[src_service]
        api_id = api_to_id[api]
        proto_id = protocol_to_id[protocol]
        dst_id = service_to_id[dst_service]

        # Edge features: [message_count, edge_type, request_count, response_count, 
        #                 avg_response_time, max_response_time, prom_features(8)]
        # Total: 14 features per edge
        
        base_features = [message_count, request_count, response_count, avg_response_time, max_response_time]
        
        # Edge 1: Service → API (edge_type=1)
        edge_list.append([src_id, api_id])
        edge_type_list.append('service_to_api')
        edge_feature_list.append(base_features + [1] + prom_edge_features.tolist())

        # Edge 2: API → Protocol (edge_type=2)
        edge_list.append([api_id, proto_id])
        edge_type_list.append('api_to_protocol')
        edge_feature_list.append(base_features + [2] + prom_edge_features.tolist())

        # Edge 3: Protocol → Service (edge_type=3)
        edge_list.append([proto_id, dst_id])
        edge_type_list.append('protocol_to_service')
        edge_feature_list.append(base_features + [3] + prom_edge_features.tolist())

    if len(edge_list) == 0:
        return np.array([[], []], dtype=np.int64), [], np.zeros((0, 14))

    edge_index = np.array(edge_list, dtype=np.int64).T
    edge_features = np.array(edge_feature_list, dtype=np.float32)
    edge_features = normalize_edge_features(edge_features)


    return edge_index, edge_type_list, edge_features  # Fixed: was 'edge_types'


def build_graph_for_window(
    window_start, window_end,
    prom_df, protocol_df, nf_df,
    service_to_id, api_to_id, protocol_to_id,
    graph_id
):
    """Build a single graph snapshot for a time window"""

    # Filter data for this window
    prom_window = prom_df[
        (prom_df['timestamp'] >= window_start) &
        (prom_df['timestamp'] < window_end)
    ]

    protocol_window = protocol_df[
        (protocol_df['timestamp'] >= window_start) &
        (protocol_df['timestamp'] < window_end)
    ].copy()

    nf_window = nf_df[
        (nf_df['timestamp'] >= window_start) &
        (nf_df['timestamp'] < window_end)
    ]

    # Add normalized columns to protocol window
    protocol_window['src_normalized'] = protocol_window['src_pod_name'].apply(normalize_service_name)
    protocol_window['dst_normalized'] = protocol_window['dst_pod_name'].apply(normalize_service_name)
    protocol_window['protocol_node'] = protocol_window['protocol'].apply(get_protocol_node_name)
    protocol_window['matched_api'] = protocol_window['api_endpoint'].apply(
        lambda x: find_matching_api(x, api_to_id)
    )

    # Build node features
    total_nodes = len(service_to_id) + len(api_to_id) + len(protocol_to_id)
    
    # Feature dimensions (updated with more Prometheus features):
    # - Prometheus features: 20 (5 metric types × 4 stats each)
    # - Protocol features for services: 16
    # - NF event features: 12
    # Total for services: 48
    # - API node features: 16
    # - Protocol node features: 16
    max_features = 50

    node_features = np.zeros((total_nodes, max_features), dtype=np.float32)

    # Service node features
    for service_name, node_id in service_to_id.items():
        # Prometheus features (20 dims - expanded)
        prom_features = extract_service_features_prometheus(prom_window, service_name)
        
        # Protocol features (16 dims)
        proto_features = extract_service_features_protocol(protocol_window, service_name)
        
        # NF event features (12 dims)
        nf_features = extract_service_features_nf(nf_window, service_name)

        # Concatenate all features
        combined = np.concatenate([prom_features, proto_features, nf_features])
        
        # Pad or truncate to max_features
        if len(combined) >= max_features:
            node_features[node_id] = combined[:max_features]
        else:
            node_features[node_id, :len(combined)] = combined

    # API node features (16 dims)
    for api, node_id in api_to_id.items():
        features = extract_api_features(protocol_window, api, api_to_id)
        node_features[node_id, :len(features)] = features

    # Protocol node features (16 dims)
    for protocol, node_id in protocol_to_id.items():
        features = extract_protocol_features(protocol_window, protocol)
        node_features[node_id, :len(features)] = features

    # Log transform high-variance features (counts)
    for i in range(node_features.shape[1]):
        col = node_features[:, i]
        if col.max() > 100:
            node_features[:, i] = np.log1p(col)

    # Extract edges (now with Prometheus features - 14 edge features)
    edge_index, edge_types, edge_features = extract_edges_and_features(
        protocol_window, prom_window, service_to_id, api_to_id, protocol_to_id
    )

    # Create PyG Data object
    data = Data(
        x=torch.tensor(node_features, dtype=torch.float),
        edge_index=torch.tensor(edge_index, dtype=torch.long),
        edge_attr=torch.tensor(edge_features, dtype=torch.float),
        timestamp=window_start,
        graph_id=graph_id,
        num_service_nodes=len(service_to_id),
        num_api_nodes=len(api_to_id),
        num_protocol_nodes=len(protocol_to_id)
    )

    return data


# ============================================================================
# Node Mapping Functions
# ============================================================================
def create_node_mappings():
    """Create fixed node ID mappings based on fullgraph.md specification"""

    # Service nodes: IDs 0-7
    service_to_id = {name: idx for idx, name in enumerate(SERVICE_NODES)}

    # API nodes: IDs 8 onwards
    api_to_id = {api: len(SERVICE_NODES) + idx for idx, api in enumerate(API_NODES)}

    # Protocol nodes: after API nodes
    protocol_to_id = {
        proto: len(SERVICE_NODES) + len(API_NODES) + idx
        for idx, proto in enumerate(PROTOCOL_NODES)
    }

    total_nodes = len(SERVICE_NODES) + len(API_NODES) + len(PROTOCOL_NODES)

    print(f"\nNode mappings created (fullgraph.md specification):")
    print(f"  Service nodes: {len(service_to_id)} (IDs 0-{len(service_to_id)-1})")
    print(f"    {SERVICE_NODES}")
    print(f"  API nodes: {len(api_to_id)} (IDs {len(SERVICE_NODES)}-{len(SERVICE_NODES)+len(API_NODES)-1})")
    print(f"  Protocol nodes: {len(protocol_to_id)} (IDs {len(SERVICE_NODES)+len(API_NODES)}-{total_nodes-1})")
    print(f"    {PROTOCOL_NODES}")
    print(f"  Total nodes: {total_nodes}")

    return service_to_id, api_to_id, protocol_to_id


# Global lookup tables for optimized API matching
_api_exact_lookup = {}
_api_normalized_lookup = {}
_api_protocol_lookup = {'NGAP:': {}, 'NAS:': {}, 'PFCP:': {}}

def initialize_api_lookups(api_to_id):
    """Pre-compute API lookup tables for O(1) matching"""
    global _api_exact_lookup, _api_normalized_lookup, _api_protocol_lookup
    
    _api_exact_lookup = {api: api for api in api_to_id.keys()}
    
    # Pre-normalize all HTTP APIs
    for api in api_to_id.keys():
        if api.startswith('/'):
            normalized = re.sub(r'\{[^}]+\}', '{id}', api)
            _api_normalized_lookup[normalized] = api
            
            # Also store by service prefix for partial matching
            parts = api.split('/')
            if len(parts) >= 3:
                prefix_key = f"{parts[1]}:{len(parts)}"
                if prefix_key not in _api_normalized_lookup:
                    _api_normalized_lookup[prefix_key] = api
        
        # Pre-index protocol messages
        for proto_prefix in ['NGAP:', 'NAS:', 'PFCP:']:
            if api.startswith(proto_prefix):
                msg_type = api[len(proto_prefix):].lower()
                _api_protocol_lookup[proto_prefix][msg_type] = api

def find_matching_api(api_endpoint, api_to_id):
    """Find matching API node for an endpoint (optimized with pre-computed lookups)"""
    if not api_endpoint:
        return None
    
    # Direct match (O(1))
    if api_endpoint in _api_exact_lookup:
        return api_endpoint
    
    # HTTP APIs: normalize and lookup
    if api_endpoint.startswith('/'):
        normalized = re.sub(r'\{[^}]+\}', '{id}', api_endpoint)
        if normalized in _api_normalized_lookup:
            return _api_normalized_lookup[normalized]
        
        # Try service prefix match
        parts = api_endpoint.split('/')
        if len(parts) >= 3:
            prefix_key = f"{parts[1]}:{len(parts)}"
            if prefix_key in _api_normalized_lookup:
                return _api_normalized_lookup[prefix_key]
    
    # Protocol messages: use pre-indexed lookup
    for proto_prefix, lookup_dict in _api_protocol_lookup.items():
        if api_endpoint.startswith(proto_prefix):
            msg_type = api_endpoint[len(proto_prefix):].lower()
            if msg_type in lookup_dict:
                return lookup_dict[msg_type]
    
    return None


def parse_prometheus_column(col_name):
    """Parse a Prometheus column name (JSON format) to extract labels"""
    if not col_name.startswith('{'):
        return None
    
    try:
        # Handle both single and double quotes
        label_dict = json.loads(col_name.replace("'", '"'))
        return label_dict
    except (json.JSONDecodeError, ValueError):
        return None


def get_metric_category(metric_name):
    """Determine the category of a Prometheus metric"""
    if not metric_name:
        return None
    
    metric_lower = metric_name.lower()
    
    for category, patterns in PROMETHEUS_METRIC_PATTERNS.items():
        for pattern in patterns:
            if pattern.lower() in metric_lower:
                return category
    
    # Fallback pattern matching
    if 'cpu' in metric_lower:
        return 'cpu'
    elif 'memory' in metric_lower or 'mem' in metric_lower:
        return 'memory'
    elif 'error' in metric_lower:
        return 'error_rate'
    elif 'request' in metric_lower and 'rate' in metric_lower:
        return 'request_rate'
    elif 'response_time' in metric_lower or 'latency' in metric_lower:
        return 'latency'
    elif 'registration_time' in metric_lower:
        return 'registration_time'
    
    return None


# ============================================================================
# Parallel Graph Building
# ============================================================================
def build_graph_for_window_wrapper(args):
    """Wrapper for parallel processing - accepts pre-filtered window data"""
    window_idx, window_start, prom_window, protocol_window, nf_window, service_to_id, api_to_id, protocol_to_id = args
    
    # Build node features
    total_nodes = len(service_to_id) + len(api_to_id) + len(protocol_to_id)
    max_features = 50
    node_features = np.zeros((total_nodes, max_features), dtype=np.float32)

    # Service node features
    for service_name, node_id in service_to_id.items():
        prom_features = extract_service_features_prometheus(prom_window, service_name)
        proto_features = extract_service_features_protocol(protocol_window, service_name)
        nf_features = extract_service_features_nf(nf_window, service_name)
        combined = np.concatenate([prom_features, proto_features, nf_features])
        if len(combined) >= max_features:
            node_features[node_id] = combined[:max_features]
        else:
            node_features[node_id, :len(combined)] = combined

    # API node features
    for api, node_id in api_to_id.items():
        features = extract_api_features(protocol_window, api, api_to_id)
        node_features[node_id, :len(features)] = features

    # Protocol node features
    for protocol, node_id in protocol_to_id.items():
        features = extract_protocol_features(protocol_window, protocol)
        node_features[node_id, :len(features)] = features

    # Log transform high-variance features
    for i in range(node_features.shape[1]):
        col = node_features[:, i]
        if col.max() > 100:
            node_features[:, i] = np.log1p(col)

    # Extract edges
    edge_index, edge_types, edge_features = extract_edges_and_features(
        protocol_window, prom_window, service_to_id, api_to_id, protocol_to_id
    )
    
    # Return numpy arrays to avoid PyTorch multiprocessing issues
    return {
        'x': node_features,
        'edge_index': edge_index,
        'edge_attr': edge_features,
        'timestamp': window_start,
        'graph_id': window_idx,
        'num_service_nodes': len(service_to_id),
        'num_api_nodes': len(api_to_id),
        'num_protocol_nodes': len(protocol_to_id)
    }


def build_graphs_parallel(windows, prom_df, protocol_df, nf_df, service_to_id, api_to_id, protocol_to_id):
    """Build graphs in parallel using multiprocessing with pre-filtered data"""
    print(f"\nBuilding graphs using {NUM_WORKERS} workers...")
    print("Pre-filtering data by time windows (this eliminates data transfer overhead)...")
    
    # Pre-filter data for each window ONCE (huge speedup)
    args_list = []
    for idx, (window_start, window_end) in enumerate(windows):
        # Filter data for this specific window
        prom_window = prom_df[
            (prom_df['timestamp'] >= window_start) &
            (prom_df['timestamp'] < window_end)
        ].copy()
        
        protocol_window = protocol_df[
            (protocol_df['timestamp'] >= window_start) &
            (protocol_df['timestamp'] < window_end)
        ].copy()
        
        nf_window = nf_df[
            (nf_df['timestamp'] >= window_start) &
            (nf_df['timestamp'] < window_end)
        ].copy()
        
        args_list.append((idx, window_start, prom_window, protocol_window, nf_window, 
                         service_to_id, api_to_id, protocol_to_id))
        
        if (idx + 1) % 1000 == 0:
            print(f"  Pre-filtered {idx+1}/{len(windows)} windows...")
    
    print(f"Pre-filtering complete. Processing with {NUM_WORKERS} workers...")
    
    # Process in batches with larger batch size for better throughput
    batch_size = 500
    graphs = []
    
    # Create Pool once and use chunksize for better load balancing
    with Pool(NUM_WORKERS) as pool:
        for batch_start in range(0, len(args_list), batch_size):
            batch_end = min(batch_start + batch_size, len(args_list))
            batch = args_list[batch_start:batch_end]
            
            print(f"  Processing windows {batch_start+1}-{batch_end}/{len(windows)}...")
            
            # Use chunksize for better parallelization
            batch_results = pool.map(build_graph_for_window_wrapper, batch, chunksize=10)
            
            # Convert numpy arrays back to PyTorch tensors
            for result in batch_results:
                data = Data(
                    x=torch.from_numpy(result['x']) if isinstance(result['x'], np.ndarray) else torch.tensor(result['x'], dtype=torch.float),
                    edge_index=torch.from_numpy(result['edge_index']) if isinstance(result['edge_index'], np.ndarray) else torch.tensor(result['edge_index'], dtype=torch.long),
                    edge_attr=torch.from_numpy(result['edge_attr']) if isinstance(result['edge_attr'], np.ndarray) else torch.tensor(result['edge_attr'], dtype=torch.float),
                    timestamp=result['timestamp'],
                    graph_id=result['graph_id'],
                    num_service_nodes=result['num_service_nodes'],
                    num_api_nodes=result['num_api_nodes'],
                    num_protocol_nodes=result['num_protocol_nodes']
                )
                graphs.append(data)
    
    return graphs


# ============================================================================
# Main Processing Pipeline
# ============================================================================
def compute_feature_statistics(graphs):
    """Compute feature statistics from training graphs"""
    all_features = torch.cat([g.x for g in graphs], dim=0)
    
    feature_activity = (all_features != 0).float().mean(dim=0)
    active_dims = (feature_activity > 0.01).nonzero(as_tuple=True)[0]
    
    feature_mean = all_features[:, active_dims].mean(dim=0)
    feature_std = all_features[:, active_dims].std(dim=0)
    feature_std[feature_std == 0] = 1.0
    
    return {
        'active_dims': active_dims,
        'mean': feature_mean,
        'std': feature_std
    }


def apply_feature_transform(graphs, stats):
    """Apply feature transformation using pre-computed statistics"""
    active_dims = stats['active_dims']
    
    for graph in graphs:
        graph.x = graph.x[:, active_dims]
    
    return graphs


def main():
    print("="*80)
    print("SERIAL CHAIN GRAPH DATA PROCESSING (Optimized)")
    print(f"CPU Cores: {cpu_count()}, Workers: {NUM_WORKERS}")
    print("="*80)

    # Create fixed node mappings per fullgraph.md
    service_to_id, api_to_id, protocol_to_id = create_node_mappings()

    # Load data with optimized dtypes
    prom_df = load_prometheus_data(PROMETHEUS_FILE)
    protocol_df = load_protocol_events(PROTOCOL_EVENTS_FILE)
    nf_df = load_nf_events(NF_EVENTS_FILE)

    # Pre-process protocol dataframe for faster filtering
    print("\nPre-processing protocol events...")
    
    # Initialize optimized API lookup tables
    print("  Initializing API lookup tables...")
    initialize_api_lookups(api_to_id)
    
    # Process in batches to manage memory
    print("  Normalizing service names...")
    batch_size = 100000
    src_normalized = []
    dst_normalized = []
    protocol_nodes = []
    matched_apis = []
    
    for i in range(0, len(protocol_df), batch_size):
        end_idx = min(i + batch_size, len(protocol_df))
        batch = protocol_df.iloc[i:end_idx]
        
        # Vectorized operations
        src_normalized.append(batch['src_pod_name'].apply(normalize_service_name))
        dst_normalized.append(batch['dst_pod_name'].apply(normalize_service_name))
        protocol_nodes.append(batch['protocol'].apply(get_protocol_node_name))
        
        # API matching with optimized lookup
        matched_apis.append(batch['api_endpoint'].apply(
            lambda x: find_matching_api(x, api_to_id)
        ))
        
        if (i // batch_size) % 3 == 0:
            print(f"  Processed {end_idx}/{len(protocol_df)} events...")
    
    protocol_df['src_normalized'] = pd.concat(src_normalized, ignore_index=True)
    protocol_df['dst_normalized'] = pd.concat(dst_normalized, ignore_index=True)
    protocol_df['protocol_node'] = pd.concat(protocol_nodes, ignore_index=True)
    protocol_df['matched_api'] = pd.concat(matched_apis, ignore_index=True)
    
    # Convert to category to save memory
    print("  Converting to categorical types...")
    protocol_df['src_normalized'] = protocol_df['src_normalized'].astype('category')
    protocol_df['dst_normalized'] = protocol_df['dst_normalized'].astype('category')
    protocol_df['protocol_node'] = protocol_df['protocol_node'].astype('category')
    protocol_df['matched_api'] = protocol_df['matched_api'].astype('category')
    
    print(f"  Matched APIs: {protocol_df['matched_api'].notna().sum()} ({protocol_df['matched_api'].notna().sum()/len(protocol_df)*100:.1f}%)")

    # Determine time windows
    min_time = min(
        prom_df['timestamp'].min(),
        protocol_df['timestamp'].min(),
        nf_df['timestamp'].min()
    )
    max_time = max(
        prom_df['timestamp'].max(),
        protocol_df['timestamp'].max(),
        nf_df['timestamp'].max()
    )

    min_time = (min_time // WINDOW_SIZE_SECONDS) * WINDOW_SIZE_SECONDS
    max_time = ((max_time // WINDOW_SIZE_SECONDS) + 1) * WINDOW_SIZE_SECONDS

    windows = []
    current = min_time
    while current < max_time:
        windows.append((current, current + WINDOW_SIZE_SECONDS))
        current += WINDOW_SIZE_SECONDS

    print(f"\nTime range: {min_time} to {max_time}")
    print(f"Number of {WINDOW_SIZE_SECONDS}s windows: {len(windows)}")

    # Build graphs in parallel
    graphs = build_graphs_parallel(
        windows, prom_df, protocol_df, nf_df,
        service_to_id, api_to_id, protocol_to_id
    )

    print(f"\nBuilt {len(graphs)} graphs")

    # Chronological split
    train_size = int(0.7 * len(graphs))
    val_size = int(0.15 * len(graphs))

    train_graphs = graphs[:train_size]
    val_graphs = graphs[train_size:train_size + val_size]
    test_graphs = graphs[train_size + val_size:]

    print(f"\nDataset split (chronological):")
    print(f"  Training: {len(train_graphs)} graphs")
    print(f"  Validation: {len(val_graphs)} graphs")
    print(f"  Test: {len(test_graphs)} graphs")

    # Compute and apply feature reduction
    print("\nComputing feature statistics from training set...")
    feature_stats = compute_feature_statistics(train_graphs)
    active_dims = feature_stats['active_dims']
    
    print(f"  Original feature dimensions: 30")
    print(f"  Active dimensions: {len(active_dims)}")
    
    train_graphs = apply_feature_transform(train_graphs, feature_stats)
    val_graphs = apply_feature_transform(val_graphs, feature_stats)
    test_graphs = apply_feature_transform(test_graphs, feature_stats)

    # Save dataset
    print(f"\nSaving dataset to {OUTPUT_FILE}...")
    
    # Create output directory if it doesn't exist
    output_path = Path(OUTPUT_FILE)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    dataset = {
        'train': train_graphs,
        'val': val_graphs,
        'test': test_graphs,
        'node_mappings': {
            'service_to_id': service_to_id,
            'api_to_id': api_to_id,
            'protocol_to_id': protocol_to_id,
            'service_nodes': SERVICE_NODES,
            'api_nodes': API_NODES,
            'protocol_nodes': PROTOCOL_NODES,
        },
        'feature_stats': {
            'active_dims': active_dims.tolist(),
            'mean': feature_stats['mean'].tolist(),
            'std': feature_stats['std'].tolist(),
        },
        'metadata': {
            'num_service_nodes': len(SERVICE_NODES),
            'num_api_nodes': len(API_NODES),
            'num_protocol_nodes': len(PROTOCOL_NODES),
            'total_nodes': len(SERVICE_NODES) + len(API_NODES) + len(PROTOCOL_NODES),
            'feature_dim': train_graphs[0].x.shape[1],
            'edge_feature_dim': 14,
            'window_size_seconds': WINDOW_SIZE_SECONDS,
            'graph_structure': 'Service → API → Protocol → Service (3 hops)',
        }
    }

    torch.save(dataset, OUTPUT_FILE)

    print("\n" + "="*80)
    print("PROCESSING COMPLETE")
    print("="*80)
    print(f"\nGraph structure:")
    print(f"  - Service nodes: {len(SERVICE_NODES)} {SERVICE_NODES}")
    print(f"  - API nodes: {len(API_NODES)}")
    print(f"  - Protocol nodes: {len(PROTOCOL_NODES)} {PROTOCOL_NODES}")
    print(f"  - Total nodes: {len(SERVICE_NODES) + len(API_NODES) + len(PROTOCOL_NODES)}")


if __name__ == "__main__":
    main()
