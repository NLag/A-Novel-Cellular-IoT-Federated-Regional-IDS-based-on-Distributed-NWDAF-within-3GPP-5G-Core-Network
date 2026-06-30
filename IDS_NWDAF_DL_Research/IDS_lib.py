import math
import torch
import torch.nn as nn
from torch.utils.data import Dataset
import pandas as pd
import os
import torch.nn.functional as F
from sklearn.model_selection import train_test_split
from torch.utils.data import DataLoader
import numpy as np
from tqdm import tqdm, trange
import torch.optim as optim
import copy
from torch import Tensor

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Device: {DEVICE}. Device count: {torch.cuda.device_count()}")

################# Hyperparameters #################

# Every data instance is an input + label pair
# INPUT: batch size, seq size, packet size
# LABEL: batch size, seq size
# Data CONST param
NUM_CLASS = 6
if NUM_CLASS == 2 :
    CLASS_NAME = ['normal','attack']
else:
    CLASS_NAME = ['normal','coapdos','mqttflood','pingflood','portscan','tcpsyn']

NUM_REGION = 5

# Preprocessing CONST param
BATCH_SIZE = 16 # number of sequences in 1 batch
SEQ_LEN = 256 # number of packets in 1 input sequence
PACKET_LEN = 1500 # maximum bytes of 1 packet

# Training CONST param
EPOCHS = 50 # each model is trained in number of epochs
DISTILLATION_EPOCHS = 25 # number of epochs for distillation
LEARNING_RATE = 0.0001 # learning rate for Adam optimizer
DELTA_LOSS = 0.001 # minimum change in validation loss to qualify as improvement

# Temperature scaling for distillation
# 1.0 is the default temperature for softmax
STUDENT_TEMPERATURE = 1
# Distillation Hyperparameters
ALPHA = 0.1  # Balance between hard and soft targets

################# Dataset Preprocessing Function #################

class PacketSeqDataset(Dataset):
    def __init__(self, X_batches, Y_batches):
        self.X_batches = X_batches
        self.Y_batches = Y_batches

    def __len__(self):
        return len(self.X_batches)

    def __getitem__(self, idx):
        X = self.X_batches[idx]
        Y = self.Y_batches[idx]
        return X, Y
    
    def set_soft_labels(self, Y_batches):
        self.Y_batches = Y_batches
    
    def get_Y_tensor(self):
        return self.Y_batches
    
    def get_X_tensor(self):
        return self.X_batches

################## Helper Function #################

def hex_to_tensor(hex_str):
        byte_array = bytes.fromhex(hex_str)
        return torch.tensor(list(byte_array), dtype=torch.uint8)
    
def process_dataframe(df_path, quiet=True):
    """Process a single dataframe from path"""
    df = pd.read_csv(df_path)
    
    if not quiet:
        print(f"Processing {df_path}, shape: {df.shape}")
        
    df['packet_hex'] = df['packet_hex'].map(hex_to_tensor)
    df['packet_hex'] = df['packet_hex'].apply(lambda x: torch.nn.functional.pad(x, (0, PACKET_LEN - len(x))))
        
    # Convert to torch tensor
    with torch.no_grad():
        X = torch.stack(df['packet_hex'].tolist()).float()
        
        # Process labels - convert to binary if needed
        if NUM_CLASS == 2:
            Y = torch.tensor(np.where(df['label'].values > 0, 1, 0), dtype=torch.long)
        else:
            Y = torch.tensor(df['label'].values, dtype=torch.long)
            
        # Move to device
        X = X.to(DEVICE)
        Y = Y.to(DEVICE)
        
        # Split into sequences
        seq_len = SEQ_LEN
        num_complete_sequences = len(X) // seq_len
        
        if num_complete_sequences == 0:
            return [], []
            
        X_reshaped = X[:num_complete_sequences * seq_len].view(-1, seq_len, PACKET_LEN)
        Y_reshaped = Y[:num_complete_sequences * seq_len].view(-1, seq_len)
        
        return X_reshaped, Y_reshaped

################## Load Dataset Function #################

def load_centralized_dataset(train_folder_path, eval_folder_path, quiet=True, debug=False):
    """
    Load and preprocess all train dataset to form a single centralized dataset.
    
    Args:
        train_folder_path: Path to training data CSV files
        eval_folder_path: Path to evaluation data CSV files
        quiet: If True, suppress most output messages
        debug: If True, print debug information
        use_cache: (Removed) If True, try to load preprocessed data from cache
        cache_dir: (Removed) Directory to store/load cached data (defaults to train_folder_path)
    Returns:
        Tuple of (train_loaders, validation_loaders, test_loaders, eval_loaders)
    """
    ################# Get all CSV file #################
    # Check if folders exist
    if not os.path.exists(train_folder_path):
        print(f"Error: Training folder {train_folder_path} does not exist")
        return None
    if not os.path.exists(eval_folder_path):
        print(f"Error: Evaluation folder {eval_folder_path} does not exist")
        return None
    
    public_train_path = os.path.join(train_folder_path, 'public')
    private_train_path = os.path.join(train_folder_path, 'private')

    # Get list of CSV files in training folder (including public and private subfolders)
    # Get full paths for all CSV files in public and private directories
    public_files = [os.path.join(public_train_path, f) for f in os.listdir(public_train_path) if f.endswith('.csv')]
    private_files = [os.path.join(private_train_path, f) for f in os.listdir(private_train_path) if f.endswith('.csv')]
    train_files = public_files + private_files
    train_files.sort()  # Ensure consistent ordering
    
    # Get list of CSV files in evaluation folder
    eval_files = [f for f in os.listdir(eval_folder_path) if f.endswith('.csv')]
    eval_files.sort()  # Ensure consistent ordering
    
    
    ################# Process training data #################
    
    train_dataset_X_list = []
    train_dataset_Y_list = []
    
    for i, file_path in enumerate(train_files):
        if not quiet:
            print(f"Processing training file {i+1}/{len(train_files)}: {file_path}")
        resultX, resultY = process_dataframe(file_path, quiet=quiet)
        if len(resultX) > 0:
            train_dataset_X_list.append(resultX)
            train_dataset_Y_list.append(resultY)
    
    # Concatenate all batches
    train_dataset_X = torch.cat(train_dataset_X_list, dim=0)
    train_dataset_Y = torch.cat(train_dataset_Y_list, dim=0)
    
    ################# Process evaluation data #################
    
    eval_dataset_X_list = []
    eval_dataset_Y_list = []
    
    for i, filename in enumerate(eval_files):
        if not quiet:
            print(f"Processing evaluation file {i+1}/{len(eval_files)}: {filename}")
        file_path = os.path.join(eval_folder_path, filename)
        resultX, resultY = process_dataframe(file_path, quiet=quiet)
        if len(resultX) > 0:
            eval_dataset_X_list.append(resultX)
            eval_dataset_Y_list.append(resultY)
    
    # Concatenate all evaluation batches
    if eval_dataset_X_list:
        eval_dataset_X = torch.cat(eval_dataset_X_list, dim=0)
        eval_dataset_Y = torch.cat(eval_dataset_Y_list, dim=0)
    else:
        eval_dataset_X = torch.tensor([])
        eval_dataset_Y = torch.tensor([])
    
    ################# Create datasets and loaders #################
    
    # Split training data
    X_train, X_test, Y_train, Y_test = train_test_split(train_dataset_X, train_dataset_Y, test_size=0.2)
    X_train, X_val, Y_train, Y_val = train_test_split(X_train, Y_train, test_size=0.2)

    if not quiet:
        print(f"Data splits - Train: {len(X_train)}, Val: {len(X_val)}, Test: {len(X_test)}")

    # Create datasets
    train_dataset = PacketSeqDataset(X_train, Y_train)
    val_dataset = PacketSeqDataset(X_val, Y_val)
    test_dataset = PacketSeqDataset(X_test, Y_test)
    eval_dataset = PacketSeqDataset(eval_dataset_X, eval_dataset_Y) if len(eval_dataset_X) > 0 else None

    # Create DataLoader
    train_loader = DataLoader(train_dataset, batch_size=BATCH_SIZE, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=BATCH_SIZE, shuffle=False)
    test_loader = DataLoader(test_dataset, batch_size=BATCH_SIZE, shuffle=False)
    eval_loader = DataLoader(eval_dataset, batch_size=BATCH_SIZE, shuffle=False) if eval_dataset else None

    return train_loader, val_loader, test_loader, eval_loader

################# Load Region Datasets Function #################

def load_private_region_datasets(train_folder_path, eval_folder_path, quiet=True, debug=False):
    """
    Load and preprocess dataset from multiple regions. If public dataset is available, 
    it will be merged with the private dataset for each region.
    
    Args:
        train_folder_path: Path to training data CSV files
        eval_folder_path: Path to evaluation data CSV files
        quiet: If True, suppress most output messages
        debug: If True, print debug information
        use_cache: (Removed) If True, try to load preprocessed data from cache
        cache_dir: (Removed) Directory to store/load cached data (defaults to train_folder_path)
        
    Returns:
        Tuple of (train_loaders, validation_loaders, test_loaders, eval_loader)
    """
    
    ################# Get all CSV file #################
    # Check if folders exist
    if not os.path.exists(train_folder_path):
        print(f"Error: Training folder {train_folder_path} does not exist")
        return None
    if not os.path.exists(eval_folder_path):
        print(f"Error: Evaluation folder {eval_folder_path} does not exist")
        return None
    # check if inside train folder contain folder public and private
    train_public_path = os.path.join(train_folder_path, 'public')
    train_private_path = os.path.join(train_folder_path, 'private')
    if not os.path.exists(train_public_path) or not os.path.exists(train_private_path):
        print(f"Error: Training folder {train_folder_path} does not contain public and private folders")
        return None
    
    # Get list of CSV files in training folder
    train_public_files = [os.path.join(train_public_path, f) for f in os.listdir(train_public_path) if f.endswith('.csv')]
    train_public_files.sort()  # Ensure consistent ordering
    train_private_files = [os.path.join(train_private_path, f) for f in os.listdir(train_private_path) if f.endswith('.csv')]
    train_private_files.sort()  # Ensure consistent ordering
    
    # Get list of CSV files in evaluation folder
    eval_files = [f for f in os.listdir(eval_folder_path) if f.endswith('.csv')]
    eval_files.sort()  # Ensure consistent ordering
    
    global NUM_REGION
    if NUM_REGION != len(train_private_files):
        print(f"Error: Number of regions ({NUM_REGION}) does not match CSV files in training folders "
              f"(training: {len(train_private_files)}, evaluation: {len(eval_files)})")
        return None
    
    print(f"Number of regions: {NUM_REGION}")
    
    ################# Process training data #################
    
    public_train_dataset_X_list = []
    public_train_dataset_Y_list = []
    # Process public data
    for i, file_path in enumerate(train_public_files):
        if not quiet:
            print(f"Processing training file {i+1}/{len(train_public_files)}: {file_path}")
        resultX,resultY = process_dataframe(file_path, quiet=quiet)
        public_train_dataset_X_list.append(resultX)
        public_train_dataset_Y_list.append(resultY)
    
    # Concatenate all batches
    public_train_dataset_X = torch.cat(public_train_dataset_X_list, dim=0)
    public_train_dataset_Y = torch.cat(public_train_dataset_Y_list, dim=0)

    # Process private data
    private_train_dataset_list = []
    for i, file_path in enumerate(train_private_files):
        if not quiet:
            print(f"Processing training file {i+1}/{len(train_private_files)}: {file_path}")
        result = process_dataframe(file_path, quiet=quiet)
        private_train_dataset_list.append(result)
    
    ################# Process evaluation data #################
    
    eval_dataset_X_list = []
    eval_dataset_Y_list = []
    # Process evaluation data
    for i, filename in enumerate(eval_files):
        if not quiet:
            print(f"Processing evaluation file {i+1}/{len(eval_files)}: {filename}")
        file_path = os.path.join(eval_folder_path, filename)
        resultX, resultY = process_dataframe(file_path, quiet=quiet)
        if len(resultX) > 0:
            eval_dataset_X_list.append(resultX)
            eval_dataset_Y_list.append(resultY)

    # Concatenate all evaluation batches
    if eval_dataset_X_list:
        eval_dataset_X = torch.cat(eval_dataset_X_list, dim=0)
        eval_dataset_Y = torch.cat(eval_dataset_Y_list, dim=0)
    else:
        eval_dataset_X = torch.tensor([])
        eval_dataset_Y = torch.tensor([])

    ################# Create datasets and loaders #################

    train_loaders = []
    validation_loaders = []
    test_loaders = []
    
    for i in range(len(train_private_files)):
        X_batches, Y_batches = private_train_dataset_list[i]
        # merge public and private data
        if len(public_train_dataset_X) > 0:
            X_batches = torch.cat((public_train_dataset_X, X_batches), dim=0)
            Y_batches = torch.cat((public_train_dataset_Y, Y_batches), dim=0)
        
        if len(X_batches) == 0:
            print(f"Warning: Region {i+1} has no complete sequences, skipping")
            # Add empty loaders
            train_loaders.append(DataLoader(PacketSeqDataset([], []), batch_size=BATCH_SIZE))
            validation_loaders.append(DataLoader(PacketSeqDataset([], []), batch_size=BATCH_SIZE))
            test_loaders.append(DataLoader(PacketSeqDataset([], []), batch_size=BATCH_SIZE))
            continue
            
        # Split data
        X_train, X_test, Y_train, Y_test = train_test_split(X_batches, Y_batches, test_size=0.2)
        X_train, X_val, Y_train, Y_val = train_test_split(X_train, Y_train, test_size=0.2)
        
        if not quiet:
            print(f"Region {i+1} splits - X Shape:{X_train[0].shape}, Y Shape:{Y_train[0].shape}, Train: {len(X_train)}, Val: {len(X_val)}, Test: {len(X_test)}")
        
        # Create datasets
        train_dataset = PacketSeqDataset(X_train, Y_train)
        val_dataset = PacketSeqDataset(X_val, Y_val)
        test_dataset = PacketSeqDataset(X_test, Y_test)

        # Create DataLoader
        train_loader = DataLoader(train_dataset, batch_size=BATCH_SIZE, shuffle=True)
        val_loader = DataLoader(val_dataset, batch_size=BATCH_SIZE, shuffle=False)
        test_loader = DataLoader(test_dataset, batch_size=BATCH_SIZE, shuffle=False)
        train_loaders.append(train_loader)
        validation_loaders.append(val_loader)
        test_loaders.append(test_loader)
    
    # Process evaluation DataLoader
    eval_dataset = PacketSeqDataset(eval_dataset_X, eval_dataset_Y)
    eval_loader = DataLoader(eval_dataset, batch_size=BATCH_SIZE, shuffle=False)
    
    return train_loaders, validation_loaders, test_loaders, eval_loader


################# Load Public and Private Datasets Function #################
def load_public_and_private_datasets(train_folder_path, eval_folder_path, quiet=True, debug=False):
    """
    Load and preprocess dataset for multiple regions, but separate the public dataset 
    and the regional private dataset.
    
    Args:
        train_folder_path: Path to training data CSV files
        eval_folder_path: Path to evaluation data CSV files
        quiet: If True, suppress most output messages
        debug: If True, print debug information
        use_cache: (Removed) If True, try to load preprocessed data from cache
        cache_dir: (Removed) Directory to store/load cached data (defaults to train_folder_path)
        
    Returns:
        Tuple of (public_data_loaders, private_train_loaders, private_validation_loaders, private_test_loaders, eval_loader)
    """
    
    ################# Get all CSV file #################
    # Check if folders exist
    if not os.path.exists(train_folder_path):
        print(f"Error: Training folder {train_folder_path} does not exist")
        return None
    if not os.path.exists(eval_folder_path):
        print(f"Error: Evaluation folder {eval_folder_path} does not exist")
        return None
    # check if inside train folder contain folder public and private
    train_public_path = os.path.join(train_folder_path, 'public')
    train_private_path = os.path.join(train_folder_path, 'private')
    if not os.path.exists(train_public_path) or not os.path.exists(train_private_path):
        print(f"Error: Training folder {train_folder_path} does not contain public and private folders")
        return None
    
    # Get list of CSV files in training folder
    train_public_files = [f for f in os.listdir(train_public_path) if f.endswith('.csv')]
    train_public_files.sort()  # Ensure consistent ordering
    train_private_files = [f for f in os.listdir(train_private_path) if f.endswith('.csv')]
    train_private_files.sort()  # Ensure consistent ordering
    
    # Get list of CSV files in evaluation folder
    eval_files = [f for f in os.listdir(eval_folder_path) if f.endswith('.csv')]
    eval_files.sort()  # Ensure consistent ordering
    
    global NUM_REGION
    if NUM_REGION != len(train_private_files):
        print(f"Error: Number of regions ({NUM_REGION}) does not match CSV files in training folders "
              f"(training: {len(train_private_files)}, evaluation: {len(eval_files)})")
        return None
    
    print(f"Number of regions: {NUM_REGION}")   
    
    ################# Process training data #################
    
    public_train_dataset_X_list = []
    public_train_dataset_Y_list = []
    # Process public data
    for i, filename in enumerate(train_public_files):
        if not quiet:
            print(f"Processing training file {i+1}/{len(train_public_files)}: {filename}")
        file_path = os.path.join(train_public_path, filename)
        resultX,resultY = process_dataframe(file_path, quiet=quiet)
        public_train_dataset_X_list.append(resultX)
        public_train_dataset_Y_list.append(resultY)
    
    # Concatenate all batches
    public_train_dataset_X = torch.cat(public_train_dataset_X_list, dim=0)
    public_train_dataset_Y = torch.cat(public_train_dataset_Y_list, dim=0)

    
    private_train_dataset_list = []
    # Process private data
    for i, filename in enumerate(train_private_files):
        if not quiet:
            print(f"Processing training file {i+1}/{len(train_private_files)}: {filename}")
        file_path = os.path.join(train_private_path, filename)
        result = process_dataframe(file_path, quiet=quiet)
        private_train_dataset_list.append(result)
    
    ################# Process evaluation data #################
    
    eval_dataset_X_list = []
    eval_dataset_Y_list = []
    # Process evaluation data
    for i, filename in enumerate(eval_files):
        if not quiet:
            print(f"Processing evaluation file {i+1}/{len(eval_files)}: {filename}")
        file_path = os.path.join(eval_folder_path, filename)
        resultX, resultY = process_dataframe(file_path, quiet=quiet)
        if len(resultX) > 0:
            eval_dataset_X_list.append(resultX)
            eval_dataset_Y_list.append(resultY)

    # Concatenate all evaluation batches
    if eval_dataset_X_list:
        eval_dataset_X = torch.cat(eval_dataset_X_list, dim=0)
        eval_dataset_Y = torch.cat(eval_dataset_Y_list, dim=0)
    else:
        eval_dataset_X = torch.tensor([])
        eval_dataset_Y = torch.tensor([])

    # # Store both individual region results and combined dataset
    # eval_dataset_list = []
    # for i, filename in enumerate(eval_files):
    #     if not quiet:
    #         print(f"Processing evaluation file {i+1}/{len(eval_files)}: {filename}")
    #     file_path = os.path.join(eval_folder_path, filename)
    #     result = process_dataframe(file_path, quiet=quiet)
    #     eval_dataset_list.append(result)

    ################# Create datasets and loaders #################

    # Create DataLoader for public data
    if len(public_train_dataset_X) == 0:
        print(f"Warning: Public dataset has no complete sequences, skipping")
        # Add empty loaders
        public_data_loaders = None
    else:
        # Split data
        X_train, X_val, Y_train, Y_val = train_test_split(public_train_dataset_X, public_train_dataset_Y, test_size=0.2)
        # X_train, X_val, Y_train, Y_val = train_test_split(X_train, Y_train, test_size=0.2)
    
        if not quiet:
            # print(f"Public splits: X Shape:{X_train[0].shape}, Y Shape:{Y_train[0].shape}, Train: {len(X_train)}, Val: {len(X_val)}, Test: {len(X_test)}")
            print(f"Public splits: X Shape:{X_train[0].shape}, Y Shape:{Y_train[0].shape}, Train: {len(X_train)}, Val: {len(X_val)}")
    
        # Create datasets
        train_dataset = PacketSeqDataset(X_train, Y_train)
        val_dataset = PacketSeqDataset(X_val, Y_val)
        # test_dataset = PacketSeqDataset(X_test, Y_test)

        # Create DataLoader
        public_train_loader = DataLoader(train_dataset, batch_size=BATCH_SIZE, shuffle=True)
        public_val_loader = DataLoader(val_dataset, batch_size=BATCH_SIZE, shuffle=False)
        # public_test_loader = DataLoader(test_dataset, batch_size=BATCH_SIZE, shuffle=False)

        # Create a dict to save public data loaders
        public_data_loaders = {
            'train': public_train_loader,
            'validation': public_val_loader
            # 'test': public_test_loader
        }

    # Create DataLoader for private data
    private_train_loaders = []
    private_validation_loaders = []
    private_test_loaders = []
    
    for i in range(len(private_train_dataset_list)):
        X_batches, Y_batches = private_train_dataset_list[i]
        
        if len(X_batches) == 0:
            print(f"Warning: Region {i+1} has no complete sequences, skipping")
            # Add empty loaders
            private_train_loaders.append(DataLoader(PacketSeqDataset([], []), batch_size=BATCH_SIZE))
            private_validation_loaders.append(DataLoader(PacketSeqDataset([], []), batch_size=BATCH_SIZE))
            private_test_loaders.append(DataLoader(PacketSeqDataset([], []), batch_size=BATCH_SIZE))
            continue
            
        # Split data
        X_train, X_test, Y_train, Y_test = train_test_split(X_batches, Y_batches, test_size=0.2)
        X_train, X_val, Y_train, Y_val = train_test_split(X_train, Y_train, test_size=0.2)
        
        if not quiet:
            print(f"Region {i+1} splits - X Shape:{X_train[0].shape}, Y Shape:{Y_train[0].shape}, Train: {len(X_train)}, Val: {len(X_val)}, Test: {len(X_test)}")
        
        # Create datasets
        train_dataset = PacketSeqDataset(X_train, Y_train)
        val_dataset = PacketSeqDataset(X_val, Y_val)
        test_dataset = PacketSeqDataset(X_test, Y_test)

        # Create DataLoader
        train_loader = DataLoader(train_dataset, batch_size=BATCH_SIZE, shuffle=True)
        val_loader = DataLoader(val_dataset, batch_size=BATCH_SIZE, shuffle=False)
        test_loader = DataLoader(test_dataset, batch_size=BATCH_SIZE, shuffle=False)
        private_train_loaders.append(train_loader)
        private_validation_loaders.append(val_loader)
        private_test_loaders.append(test_loader)

    # # Process evaluation dataset
    # for i in range(NUM_REGION):
    #     X_eval_batches, Y_eval_batches = eval_dataset_list[i]
        
    #     eval_dataset = PacketSeqDataset(X_eval_batches, Y_eval_batches)
    #     eval_loader = DataLoader(eval_dataset, batch_size=BATCH_SIZE, shuffle=False)
    #     eval_loaders.append(eval_loader)

    # Process evaluation DataLoader
    eval_dataset = PacketSeqDataset(eval_dataset_X, eval_dataset_Y)
    eval_loader = DataLoader(eval_dataset, batch_size=BATCH_SIZE, shuffle=False)
    
    return public_data_loaders, private_train_loaders, private_validation_loaders, private_test_loaders, eval_loader


################# Training Function #################

def train_one_epoch(model, train_loader, optimizer, loss_fn, quiet=True, debug=False):
    running_loss = 0.

    # Create progress bar for batches if debugging
    if debug:
        pbar = tqdm(enumerate(train_loader), total=len(train_loader), 
                   desc="  Training batches", leave=False)
    else:
        pbar = enumerate(train_loader)

    # Here, we use enumerate(train_loader) instead of
    # iter(train_loader) so that we can track the batch
    # index and do some intra-epoch reporting
    for i, data in pbar:
        # Every data instance is an input + label pair
        # INPUT: batch size, seq size, feature size
        # LABEL: batch size, seq size (class index) 
        #        batch size, seq size, class size (one-hot / softmax)

        # Get the inputs; data is a list of [inputs, labels]
        inputs, labels = data

        if labels.shape[-1] != NUM_CLASS: # if labels are class index
            # Convert labels to one-hot encoding
            labels = F.one_hot(labels, num_classes=NUM_CLASS).float()
        
        # Convert labels to (batch size x seq size, class size) 
        labels = labels.view(-1, NUM_CLASS)

        # Zero your gradients for every batch!
        optimizer.zero_grad()

        # Make predictions for this batch
        outputs = model(inputs)

        # Compute the loss and its gradients
        loss = loss_fn(outputs.view(-1,NUM_CLASS), labels)
        loss.backward()

        # Adjust learning weights
        optimizer.step()

        # Gather data and report
        running_loss += loss.item()

        if (i+1) % 10 == 0:
            last_loss = running_loss / (i+1) # update average loss every 10 batch
            if debug and isinstance(pbar, tqdm):
                pbar.set_postfix(loss=f"{last_loss:.4f}")
    # Calculate average loss over the epoch
    if len(train_loader) > 0:
        avg_epoch_loss = running_loss / len(train_loader)
    else:
        avg_epoch_loss = 0.0

    return avg_epoch_loss

# Train model function
def training_model(model, train_loader, validation_loader, epochs=EPOCHS, patience=5, min_delta=DELTA_LOSS, quiet=True, debug=False, model_name='0'):
    '''
    Train model with early stopping
    
    Args:
        model: The neural network model to train
        train_loader: DataLoader for training data
        validation_loader: DataLoader for validation data
        epochs: Maximum number of epochs to train
        patience: Number of epochs with no improvement after which training will stop
        min_delta: Minimum change in validation loss to qualify as improvement
        quiet: If True, suppress some output
    '''
    # Device configuration
    model.to(DEVICE)

    loss_fn = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=LEARNING_RATE)

    best_vloss = float('inf')
    epochs_no_improve = 0
    early_stop = False
    best_model_state = None

    # Create progress bar for epochs
    if not quiet:
        epoch_pbar = trange(epochs, desc=f"Model {model_name} Epochs", leave=False)
    else:
        epoch_pbar = range(epochs)

    for epoch in epoch_pbar:
        if early_stop:
            if best_model_state:
                # Restore the best model
                model.load_state_dict(best_model_state)
            break

        # Make sure gradient tracking is on, and do a pass over the data
        model.train(True)
        avg_loss = train_one_epoch(model, train_loader, optimizer, loss_fn, quiet, debug)

        running_vloss = 0.0
        # Set the model to evaluation mode
        model.eval()
        
        # Disable gradient computation and reduce memory consumption.
        with torch.no_grad():
            for i, vdata in enumerate(validation_loader):
                vinputs, vlabels = vdata
                if vlabels.shape[-1] != NUM_CLASS: # if labels are not one-hot
                    # Convert labels to one-hot encoding
                    vlabels = F.one_hot(vlabels, num_classes=NUM_CLASS).float()
                # Convert labels to (batch size x seq size, class size) 
                vlabels = vlabels.view(-1, NUM_CLASS)
                voutputs = model(vinputs)
                vloss = loss_fn(voutputs.view(-1,NUM_CLASS), vlabels)
                running_vloss += vloss

        avg_vloss = running_vloss / (i + 1)
        # Update progress bar with loss values if it's a tqdm object
        if not quiet and isinstance(epoch_pbar, tqdm):
            epoch_pbar.set_postfix(train_loss=f"{avg_loss:.4f}", val_loss=f"{avg_vloss:.4f}")
        
        # Early stopping check
        if avg_vloss < best_vloss - min_delta:
            best_vloss = avg_vloss
            epochs_no_improve = 0
            # Save the best model state
            best_model_state = copy.deepcopy(model.state_dict())
        elif avg_vloss > best_vloss + min_delta:
            # fluctuation in validation loss (e.g., due to noise in data)
            # may escape local minima in future epochs
            epochs_no_improve = 0
        else:
            epochs_no_improve += 1
            # if not quiet:
            #     print(f'  No improvement for {epochs_no_improve} epochs')
            if epochs_no_improve >= patience:
                # if not quiet:
                #     print('  Early stopping!')
                early_stop = True
    if early_stop and debug:
        print('Early stopping triggered at epoch', epoch)
    return best_vloss

################### Distillation Training Function #################

def distillation_one_epoch(model, train_loader, teacher_train_softlabel_loader, optimizer, loss_fn, quiet=True, debug=False):
    '''
    Train model with distillation for one epoch
    Args:
        model: The neural network model to train
        train_loader: DataLoader for training data
        teacher_train_softlabel_loader: DataLoader for teacher logits
        optimizer: Optimizer for the model
        loss_fn: Loss function for the model
        quiet: If True, suppress some output
        debug: If True, print debug information
    '''
    running_loss = 0.
    
    # Create iterators for both data loaders
    train_iterator = iter(train_loader)
    teacher_iterator = iter(teacher_train_softlabel_loader)

    # Create progress bar for batches if debugging
    # Ensure both loaders have the same number of batches
    assert len(train_loader) == len(teacher_train_softlabel_loader), "Train loader and teacher softlabel loader must have the same number of batches"
    total_batches = len(train_loader)
    if debug:
        pbar = tqdm(range(total_batches), 
                   desc="  Distillation Training batches", leave=False)
    else:
        pbar = range(total_batches)

    # Here, we iterate through both loaders in parallel
    for i in pbar:
        # Every data instance is an input + label pair
        # INPUT: batch size, seq size, feature size
        # LABEL: batch size, seq size (class index) 
        #        batch size, seq size, class size (one-hot / softmax)
        try:
            # Get the inputs from train loader
            data = next(train_iterator)
            inputs, labels = data
            
            # Get the soft labels (probabilities) from the teacher model
            teacher_data = next(teacher_iterator)
            teacher_soft_labels = teacher_data[1]
        except StopIteration:
            break

        if labels.shape[-1] != NUM_CLASS: # if labels are class index
            # Convert labels to one-hot encoding
            labels = F.one_hot(labels, num_classes=NUM_CLASS).float()
        if teacher_soft_labels.shape[-1] != NUM_CLASS: # if labels are class index
            # Convert labels to one-hot encoding
            teacher_soft_labels = F.one_hot(teacher_soft_labels, num_classes=NUM_CLASS).float()

        # Convert labels to (batch size x seq size, class size) 
        labels = labels.view(-1, NUM_CLASS)

        # Zero your gradients for every batch!
        optimizer.zero_grad()

        # Make predictions for this batch
        outputs = model(inputs)

        # Compute the loss and its gradients
        # Reshape teacher soft labels to match outputs
        teacher_soft_labels = teacher_soft_labels.view(-1, NUM_CLASS)
        
        # Apply temperature scaling if needed (optional)
        
        # Hard loss - standard cross entropy with hard labels
        hard_loss = loss_fn(outputs.view(-1, NUM_CLASS), labels)
        
        # Soft loss - KL divergence between softened distributions
        # Apply softmax with temperature to both distributions
        student_probs = F.log_softmax(outputs.view(-1, NUM_CLASS)/STUDENT_TEMPERATURE, dim=-1)
        teacher_probs = teacher_soft_labels
        
        # KL divergence requires log probabilities for predictions
        soft_loss = F.kl_div(
            student_probs,
            teacher_probs,
            reduction='batchmean'
        ) * (STUDENT_TEMPERATURE ** 2)  # Scale by temperature squared
        
        # Combined loss
        loss = (1-ALPHA)*hard_loss + ALPHA*soft_loss
        loss.backward()

        # Gradient clipping
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=2.0)
        # Adjust learning weights
        optimizer.step()

        # Gather data and report
        running_loss += loss.item()

        if (i+1) % 10 == 0:
            last_loss = running_loss / (i+1) # average running loss
            if debug and isinstance(pbar, tqdm):
                pbar.set_postfix(loss=f"{last_loss:.4f}")
    avg_loss = running_loss / (i + 1)
    return avg_loss

# Distillation model training function
def distillation_training_model(model, train_loader, teacher_train_softlabel_loader, validation_loader, teacher_validation_softlabel_loader, epochs=DISTILLATION_EPOCHS, patience=5, min_delta=DELTA_LOSS, quiet=True, debug=False, model_name='0'):
    '''
    Train model with early stopping
    
    Args:
        model: The neural network model to train
        train_loader: DataLoader for training data
        teacher_train_softlabel_loader: DataLoader for teacher soft labels
        validation_loader: DataLoader for validation data
        teacher_validation_softlabel_loader: DataLoader for teacher soft labels for validation data
        epochs: Maximum number of epochs to train
        patience: Number of epochs with no improvement after which training will stop
        min_delta: Minimum change in validation loss to qualify as improvement
        quiet: If True, suppress some output
    '''
    # Device configuration
    model.to(DEVICE)

    loss_fn = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=LEARNING_RATE, weight_decay=1e-5)

    best_vloss = float('inf')
    epochs_no_improve = 0
    early_stop = False
    best_model_state = None

    # Create progress bar for epochs
    if not quiet:
        epoch_pbar = trange(epochs, desc=f"Model {model_name} Epochs", leave=False)
    else:
        epoch_pbar = range(epochs)

    for epoch in epoch_pbar:
        if early_stop:
            # if best_model_state:
            #     # Restore the best model
            #     model.load_state_dict(best_model_state)
            break

        # Make sure gradient tracking is on, and do a pass over the data
        model.train(True)
        avg_loss = distillation_one_epoch(model, train_loader, teacher_train_softlabel_loader, optimizer, loss_fn, quiet, debug)

        running_vloss = 0.0
        # Set the model to evaluation mode
        model.eval()
        
        # Disable gradient computation and reduce memory consumption.
        # Note: teacher_validation_softlabel_loader should be the same size as validation_loader\
        assert len(validation_loader) == len(teacher_validation_softlabel_loader), "Validation loader and teacher softlabel loader must have the same number of batches"
        validation_loader_iter = iter(validation_loader)
        teacher_validation_softlabel_iter = iter(teacher_validation_softlabel_loader)
        with torch.no_grad():
            for i in range(len(validation_loader)):
                # Get the inputs from validation loader
                vdata = next(validation_loader_iter)
                vinputs, vlabels = vdata
                
                # Get the soft labels (probabilities) from the teacher model
                teacher_data = next(teacher_validation_softlabel_iter)
                teacher_soft_labels = teacher_data[1]
                
                if vlabels.shape[-1] != NUM_CLASS: # if labels are not one-hot
                    # Convert labels to one-hot encoding
                    vlabels = F.one_hot(vlabels, num_classes=NUM_CLASS).float()
                if teacher_soft_labels.shape[-1] != NUM_CLASS: # if labels are not one-hot
                    # Convert labels to one-hot encoding
                    teacher_soft_labels = F.one_hot(teacher_soft_labels, num_classes=NUM_CLASS).float()
                # else:
                #     # if labels are one-hot format, convert to softmax
                #     teacher_soft_labels = F.softmax(teacher_soft_labels/TEMPERATURE, dim=1)

                # Convert labels to (batch size x seq size, class size) 
                vlabels = vlabels.view(-1, NUM_CLASS)
                voutputs = model(vinputs)
                vhardloss = loss_fn(voutputs.view(-1,NUM_CLASS), vlabels)

                # Reshape teacher soft labels to match outputs
                teacher_soft_labels = teacher_soft_labels.view(-1, NUM_CLASS)
                # Apply softmax with temperature to both distributions
                student_probs = F.log_softmax(voutputs.view(-1, NUM_CLASS) / STUDENT_TEMPERATURE, dim=-1)
                # KL divergence requires log probabilities for predictions
                soft_loss = F.kl_div(
                    student_probs,
                    teacher_soft_labels,
                    reduction='batchmean'
                ) * (STUDENT_TEMPERATURE ** 2)  # Scale by temperature squared

                # Combined loss
                vloss = (1-ALPHA)* vhardloss + ALPHA * soft_loss

                if not torch.isnan(vloss):
                    running_vloss += vloss.item()
                # print(f"Validation loss: {vloss.item()}")
                
        # Early stopping check
        # Check for NaN values in validation loss
        if torch.isnan(vloss):
            print("NaN detected in validation loss - stopping training")
            early_stop = True
            continue

        avg_vloss = running_vloss / len(validation_loader)
        # Update progress bar with loss values if it's a tqdm object
        if not quiet and isinstance(epoch_pbar, tqdm):
            epoch_pbar.set_postfix(train_loss=f"{avg_loss:.4f}", val_loss=f"{avg_vloss:.4f}")
                    
        # Early stopping check
        if avg_vloss < best_vloss - min_delta:
            best_vloss = avg_vloss
            epochs_no_improve = 0
            # Save the best model state
            # best_model_state = copy.deepcopy(model.state_dict())
        elif avg_vloss > best_vloss + min_delta:
            # fluctuation in validation loss (e.g., due to noise in data)
            # may escape local minima in future epochs
            epochs_no_improve = 0
        else:
            epochs_no_improve += 1
            # if not quiet:
            #     print(f'  No improvement for {epochs_no_improve} epochs')
            if epochs_no_improve >= patience:
                # if not quiet:
                #     print('  Early stopping!')
                early_stop = True
    if early_stop and debug:
        print('Early stopping triggered at epoch', epoch)
    return best_vloss


################# Federated Learning Helper Function #################

# Function to calculate weight change magnitude
def calculate_weight_change(old_state_dict, new_state_dict):
    """Calculate the magnitude of weight changes between two model states"""
    if old_state_dict is None:
        return 0
        
    total_change = 0
    total_weights = 0
    
    for key in old_state_dict.keys():
        change = torch.sum(torch.abs(new_state_dict[key] - old_state_dict[key]))
        total_change += change.item()
        total_weights += old_state_dict[key].numel()
        
    return total_change / total_weights  # Average change per weight

def average_model_weights(model_list):
    """Average the weights of a list of models"""
    # Initialize with the first model's weights
    avg_state_dict = copy.deepcopy(model_list[0].state_dict()) # Deep copy to avoid modifying the original
    
    # Incrementally update with the remaining models
    for i, model in enumerate(model_list[1:], start=1):
        state_dict = model.state_dict()
        for key in avg_state_dict.keys():
            # Update using incremental mean formula: 
            # mean_n = mean_{n-1} + (x_n - mean_{n-1}) / n
            avg_state_dict[key] += (state_dict[key] - avg_state_dict[key]) / (i + 1)
    
    return avg_state_dict

################# Model Definition #################

class MLPClassifier(nn.Module):
    def __init__(self, input_features, output_dim, hidden_dim=256):
        super(MLPClassifier, self).__init__()
        self.fc1 = nn.Linear(input_features, 512)  
        self.fc2 = nn.Linear(512, hidden_dim)
        self.fc3 = nn.Linear(hidden_dim, 128)
        self.output = nn.Linear(128, output_dim)
        
    def forward(self, x):
        # INPUT: batch size, seq size, feature size
        if len(x.shape) == 2: # if input is not a batch
            x = x.unsqueeze(0)  # Add batch dimension
        x = torch.relu(self.fc1(x))
        x = torch.relu(self.fc2(x))
        x = torch.relu(self.fc3(x))
        x = self.output(x)
        return x


# CNN Classifier
class CNNClassifier(nn.Module):
    def __init__(self, input_features, output_dim):
        super(CNNClassifier, self).__init__()
        self.conv1 = nn.Conv1d(in_channels=input_features, out_channels=512, kernel_size=3, padding=1)
        self.conv2 = nn.Conv1d(in_channels=512, out_channels=256, kernel_size=3, padding=1)
        self.conv3 = nn.Conv1d(in_channels=256, out_channels=128, kernel_size=3, padding=1)
        
        # Fully connected layers
        self.fc1 = nn.Linear(128, 32)
        self.fc2 = nn.Linear(32, output_dim)

    def forward(self, x):
        # x shape: [batch_size, seq_len, features]
        if len(x.shape) == 2:
            x = x.unsqueeze(0)  # Add batch dimension
        # Transpose to [batch_size, features, seq_len] for Conv1d
        x = x.transpose(1, 2)
        x = torch.relu(self.conv1(x))        
        x = torch.relu(self.conv2(x))
        x = torch.relu(self.conv3(x))
        # Transpose to [batch_size, seq_len, features] for FC
        x = x.transpose(1, 2)
        x = torch.relu(self.fc1(x))
        x = self.fc2(x)
        return x

# RNN Classifier
class RNNClassifier(nn.Module):
    def __init__(self, input_features, hidden_dim, output_dim, num_layers=1):
        super(RNNClassifier, self).__init__()
        self.fc1 = nn.Linear(input_features, 512)  # Initial linear layer to reduce input size
        self.rnn = nn.RNN(512, hidden_dim, num_layers, batch_first=True, nonlinearity='relu')
        self.fc = nn.Linear(hidden_dim, output_dim)  # Output layer for classification

    def forward(self, x):
        # x shape: [batch_size, seq_len, input_features]
        if len(x.shape) == 2:
            x = x.unsqueeze(0) # Add batch dimension
        # Process sequence
        x = torch.relu(self.fc1(x))  # Apply initial fc layer
        out, hn = self.rnn(x)  # out shape: [batch_size, seq_len, hidden_dim]
        out = self.fc(out)  # Apply fc to each time step: [batch_size, seq_len, output_dim]
        return out

# LSTM Classifier
class LSTMClassifier(nn.Module):
    def __init__(self, input_features, hidden_dim, output_dim, num_layers=1):
        """
        LSTM classifier for sequence of packets
        Expects input_features=1500 (packet size)
        """
        super(LSTMClassifier, self).__init__()
        self.fc1 = nn.Linear(input_features, 512) # Initial linear layer to reduce input size
        self.lstm = nn.LSTM(512, hidden_dim, num_layers, batch_first=True)
        self.fc = nn.Linear(hidden_dim, output_dim)  # Output layer for classification

    def forward(self, x):
        """
        x shape: [batch_size, seq_len=64, input_features=1500]
        output shape: [batch_size, seq_len=64, output_dim]
        """
        if len(x.shape) == 2:
            x = x.unsqueeze(0)
        # Process sequence
        x = torch.relu(self.fc1(x))  # Apply initial fc layer
        out, (_, _) = self.lstm(x)  # out shape: [batch_size, seq_len, hidden_dim]
        # Apply fc to each time step: [batch_size, seq_len, output_dim]
        out = self.fc(out)  # Classify each element in sequence
        return out
    
# GRU Classifier
class GRUClassifier(nn.Module):
    def __init__(self, input_features, hidden_dim, output_dim, num_layers=1):
        super(GRUClassifier, self).__init__()
        self.fc1 = nn.Linear(input_features, 512)  # Initial linear layer to reduce input size
        self.gru = nn.GRU(512, hidden_dim, num_layers, batch_first=True)
        self.fc = nn.Linear(hidden_dim, output_dim)  # Output layer for classification

    def forward(self, x):
        """
        x shape: [batch_size, seq_len=64, input_features=1500]
        output shape: [batch_size, seq_len=64, output_dim]
        """
        if len(x.shape) == 2:
            x = x.unsqueeze(0)
        # Process sequence
        x = torch.relu(self.fc1(x))  # Apply initial fc layer
        out, hn = self.gru(x) # out shape: [batch_size, seq_len, hidden_dim]
        # Apply fc to each time step: [batch_size, seq_len, output_dim]
        out = self.fc(out)  # Classify each element in sequence
        return out

# Transformer Classifier
class TransformerClassifier(nn.Module):
    def __init__(self, input_features, hidden_dim=256, nhead=8, num_layers=2, output_dim=NUM_CLASS):
        super(TransformerClassifier, self).__init__()
        self.input_embedding = nn.Sequential(
            nn.Linear(input_features, 512),
            nn.ReLU(),
            nn.Linear(512, hidden_dim),
            nn.ReLU()
        )
        
        # Transformer encoder
        encoder_layers = nn.TransformerEncoderLayer(d_model=hidden_dim, nhead=nhead, 
                                                    dim_feedforward=hidden_dim*4, 
                                                    batch_first=True)
        self.transformer_encoder = nn.TransformerEncoder(encoder_layers, num_layers=num_layers)
        
        # Output layer
        self.output_layer = nn.Linear(hidden_dim, output_dim)
        
    def forward(self, x):
        # x shape: [batch_size, seq_len, input_features]
        if len(x.shape) == 2:
            x = x.unsqueeze(0)
        # Convert input to embedding
        x = self.input_embedding(x)  # [batch_size, seq_len, hidden_dim]
        
        # Pass through transformer
        x = self.transformer_encoder(x)  # [batch_size, seq_len, hidden_dim]
        
        # Project to output classes
        output = self.output_layer(x)  # [batch_size, seq_len, output_dim]

        return output

# Two Level Transformer Classifier with Positional Encoding
class PositionalEncoding(nn.Module):

    def __init__(self, d_model: int, dropout: float = 0.1, max_len: int = 5000):
        super().__init__()
        self.dropout = nn.Dropout(p=dropout)

        position = torch.arange(max_len).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2) * (-math.log(10000.0) / d_model))
        pe = torch.zeros(max_len, d_model)
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        pe = pe.unsqueeze(0)
        self.register_buffer('pe', pe)

    def forward(self, x: Tensor) -> Tensor:
        """
        Arguments:
            x: Tensor, shape ``[batch_size, seq_len, embedding_dim]``
        """
        x = x + self.pe[:,:x.size(1)]
        return self.dropout(x) 
    
# class ByteLevelTransformer(nn.Module):
#     def __init__(self, output_dim, byte_emb_dim=16, nhead=2, num_layers=1):
#         super(ByteLevelTransformer, self).__init__()
        
#         self.embedding_byte = nn.Embedding(256,byte_emb_dim)

#         # Positional encoding for 1500 bytes
#         self.pos_encoder = nn.Parameter(torch.zeros(1, 1500, byte_emb_dim))
#         nn.init.normal_(self.pos_encoder, mean=0, std=0.1)
        
#         # Transformer encoder
#         encoder_layers = nn.TransformerEncoderLayer(d_model=byte_emb_dim, nhead=nhead, 
#                                                    dim_feedforward=byte_emb_dim*4, 
#                                                    batch_first=True)
#         self.transformer_encoder = nn.TransformerEncoder(encoder_layers, num_layers=num_layers)
        
#         # Linear compression layer
#         self.l_compress = nn.Linear(byte_emb_dim, 1)

#         # Output projection to custom dimension
#         self.output_layer = nn.Linear(1500, output_dim)
        
#     def forward(self, x):
#         # x shape: [batch_size, seq_len, 1500] - sequence of 1500 byte as a vector
#         # Convert x to [batch_size x seq_len, 1500]
#         batch_size, seq_len, _ = x.size()

#         x = x.reshape(-1, PACKET_LEN) # [batch_size x seq_len, 1500]

#         x = self.embedding_byte(x)  # [batch_size x seq_len, 1500, hidden_dim]

#         # Add positional encoding
#         x = x + self.pos_encoder  # [batch_size x seq_len, 1500, hidden_dim]
        
#         # Pass through transformer
#         x = self.transformer_encoder(x)  # [batch_size x seq_len, 1500, hidden_dim]
        
#         # Linear compression
#         x = torch.relu(self.l_compress(x)) # [batch_size x seq_len, 1500, 1]
#         x = x.squeeze(-1)   # [batch_size x seq_len, 1500]

#         # Reshape back to [batch_size, seq_len, 1500]
#         x = x.reshape(batch_size, seq_len, -1)

#         # Project to output dimension
#         output = torch.relu(self.output_layer(x))  # [batch_size, seq_len, output_dim]
        
#         return output

class TwoLevelTransformer(nn.Module):
    '''
    Transformer model for classify packets.
    Input: sequence of packets (each packet has 1500 bytes)
    Output: classification for each packet in the sequence
    '''
    def __init__(self, input_features=1500, byte_emb_dim=16, packet_emb_dim=256, l1_nhead=2, l2_nhead=4, l1_num_layers=1, l2_num_layers=1, output_dim=8):
        super(TwoLevelTransformer, self).__init__()

        # Byte-level transformer
        # Embedding layer for byte-level input
        self.embedding_byte = nn.Embedding(256,byte_emb_dim)
        # Positional encoding for 1500 bytes
        self.pos_encoder = PositionalEncoding(byte_emb_dim, max_len=input_features)
        # Transformer encoder
        byte_encoder_layers = nn.TransformerEncoderLayer(d_model=byte_emb_dim, nhead=l1_nhead,
                                                   dim_feedforward=byte_emb_dim*2, 
                                                   batch_first=True)
        self.bytelevel_transformer = nn.TransformerEncoder(byte_encoder_layers, num_layers=l1_num_layers)
        # Linear compression layer for each byte
        self.l_compress = nn.Linear(byte_emb_dim, 1)
        # Output projection of the packet to custom dimension
        self.l_projection_layer = nn.Linear(input_features, packet_emb_dim)

        # Packet level Transformer
        packet_encoder_layers = nn.TransformerEncoderLayer(d_model=packet_emb_dim, nhead=l2_nhead, 
                                                   dim_feedforward=packet_emb_dim*2, 
                                                   batch_first=True)
        self.transformer_encoder = nn.TransformerEncoder(packet_encoder_layers, num_layers=l2_num_layers)
        
        # Output layer
        self.output_layer = nn.Linear(packet_emb_dim, output_dim)
        
    def forward(self, x):
        # x shape: [batch_size, seq_len, features = 1500] - sequence of packets of 1500 bytes
        # print(f"Input shape: {x.shape}")
        
        # Convert x to [batch_size x seq_len, 1500]
        batch_size, seq_len, _ = x.size()
        x = x.reshape(-1, PACKET_LEN) # [batch_size x seq_len, 1500]
        # print(f"After reshape: {x.shape}")

        x = self.embedding_byte(x.int())  # [batch_size x seq_len, 1500, byte_emb_dim]
        # print(f"After embedding: {x.shape}")

        # Add positional encoding
        x = self.pos_encoder(x) # [batch_size x seq_len, 1500, byte_emb_dim]
        # print(f"After positional encoding: {x.shape}")
        
        # Pass through byte level transformer
        x = self.bytelevel_transformer(x)  # [batch_size x seq_len, 1500, byte_emb_dim]
        # print(f"After byte level transformer: {x.shape}")
        
        # Linear compression
        x = torch.relu(self.l_compress(x)) # [batch_size x seq_len, 1500, 1]
        # print(f"After linear compression: {x.shape}")
        
        x = x.squeeze(-1)   # [batch_size x seq_len, 1500]
        # print(f"After squeeze: {x.shape}")

        # Reshape back to [batch_size, seq_len, 1500]
        x = x.reshape(batch_size, seq_len, -1)
        # print(f"After reshaping back: {x.shape}")

        # Project to output dimension
        x = torch.relu(self.l_projection_layer(x))  # [batch_size, seq_len, packet_emb_dim]
        # print(f"After projection: {x.shape}")

        # Pass through packet level transformer
        x = self.transformer_encoder(x)  # [batch_size, seq_len, packet_emb_dim]
        # print(f"After packet level transformer: {x.shape}")
        
        # Project to output classes
        output = self.output_layer(x)  # [batch_size, seq_len, output_dim]
        # print(f"Output shape: {output.shape}")
        
        return output