import torch
from torch.utils.data import DataLoader
import copy
from sklearn.metrics import confusion_matrix,classification_report,ConfusionMatrixDisplay,accuracy_score,f1_score
import matplotlib.pyplot as plt
from collections import defaultdict
from tqdm import tqdm, trange

from IDS_lib import *

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
QUIET = False
DEBUG = False

# Data file path
TRAIN_DATA_PATH = './datasets/simple_federated_datasets/train/'
EVAL_DATA_PATH = './datasets/simple_federated_datasets/eval/'

train_loaders, validation_loaders, test_loaders, eval_loader = load_private_region_datasets(TRAIN_DATA_PATH, EVAL_DATA_PATH, quiet=QUIET)

################### Training ###################

def train_regional_models(models, train_loaders, validation_loaders, test_loaders, quiet=True, debug=False):
    """
    Train regional models on the given dataset.
    Each model is trained on its respective region's training data.
    """
    best_vlosses = [float('inf')] * len(models)
    for i, model in enumerate(models):
        print(f"Training model for region {i+1}")
        vloss = training_model(model, train_loaders[i], validation_loaders[i], epochs=50, quiet=quiet, debug=debug, model_name=f"Regional model {i+1}")
        
        # Evaluate the model on the test dataset
        results = evaluate_centralized_model(model, test_loaders[i], quiet=quiet, debug=debug)
        print(f"Test Accuracy for region {i+1}: {results['accuracy']:.4f}%")
        # Print each class's F1 score with 4 decimal places
        print(f"Test F1 Score (per class) for region {i+1}:")
        print(", ".join([f"{score:.4f}" for i, score in enumerate(results['f1_score']['per_class'])]))
        print(f"Test F1 Score (weighted) for region {i+1}: {results['f1_score']['weighted']:.4f}")
        print(f"Test F1 Score (macro) for region {i+1}: {results['f1_score']['macro']:.4f}")

        # Print confusion matrix
        cm = results['confusion_matrix']
        print(f"Confusion Matrix for region {i+1}:\n{cm}")
        # Print separator
        print("-" * 50)
        # Store the best validation loss for each model
        if vloss < best_vlosses[i]:
            best_vlosses[i] = vloss
            # print(f"Best validation loss for region {i+1}: {best_vlosses[i]:.4f}")

    return best_vlosses

################### Evaluation ###################

def evaluate_centralized_model(model, test_loader, quiet=True, debug=False):
    """
    Evaluate the model on the test dataset
    """
    results = {}
    model.eval()

    correct = 0
    total = 0
    all_preds = []
    all_labels = []
    
    with torch.no_grad():
        for data in test_loader:
            inputs, labels = data
            outputs = model(inputs)
            predicted = torch.argmax(outputs.data, 2)
            
            total += labels.size(0) * labels.size(1)
            correct += (predicted == labels).sum().item()
            
            # Flatten for metrics calculation
            all_preds.extend(predicted.view(-1).cpu().numpy())
            all_labels.extend(labels.view(-1).cpu().numpy())

    accuracy = 100 * correct / total

    # Calculate F1 scores
    if NUM_CLASS == 2:  # Binary classification
        f1 = f1_score(all_labels, all_preds)
        f1_per_class = None  # Not needed for binary
    else:  # Multi-class classification
        f1_macro = f1_score(all_labels, all_preds, average='macro')
        f1_weighted = f1_score(all_labels, all_preds, average='weighted')
        f1_per_class = f1_score(all_labels, all_preds, average=None)
        f1 = {'macro': f1_macro, 'weighted': f1_weighted, 'per_class': f1_per_class}
    
    # Confusion matrix
    cm = confusion_matrix(all_labels, all_preds)

    results = {
            'total': total,
            'correct': correct,
            'accuracy': accuracy,
            'f1_score': f1,
            'predictions': all_preds,
            'labels': all_labels,
            'confusion_matrix': cm,
    }
    
    return results

################### Main ###################

if __name__ == "__main__":
    # Initialize the model
    models = []
    for i in range(NUM_REGION):
        model = TransformerClassifier(input_features=PACKET_LEN)
        model.to(DEVICE)
        models.append(model)

    # Train the model
    best_vlosses = train_regional_models(models, train_loaders, validation_loaders, test_loaders, quiet=QUIET, debug=DEBUG)
    
    # Evaluate the model on the evaluation dataset
    # Evaluate each model on the evaluation dataset
    for i, model in enumerate(models):
        print(f"\nEvaluating model for region {i+1} on the evaluation dataset:")
        eval_results = evaluate_centralized_model(model, eval_loader, quiet=QUIET, debug=DEBUG)
        print(f"Evaluation Accuracy: {eval_results['accuracy']:.4f}%")
        # Print each class's F1 score with 4 decimal places
        print("Evaluation F1 Score (per class):")
        print(", ".join([f"{score:.4f}" for i, score in enumerate(eval_results['f1_score']['per_class'])]))
        print(f"Evaluation F1 Score (weighted): {eval_results['f1_score']['weighted']:.4f}")
        print(f"Evaluation F1 Score (macro): {eval_results['f1_score']['macro']:.4f}")
        print(f"Evaluation Confusion Matrix:\n{eval_results['confusion_matrix']}")
        # Print separator
        print("-" * 50)