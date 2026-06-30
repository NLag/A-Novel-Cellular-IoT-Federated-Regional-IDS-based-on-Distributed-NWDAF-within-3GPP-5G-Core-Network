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
# TRAIN_DATA_PATH = './datasets/simple_federated_datasets/train/'
# EVAL_DATA_PATH = './datasets/simple_federated_datasets/eval/'

TRAIN_DATA_PATH = './datasets/federated_datasets_noslowite_nosqlmap/train/'
EVAL_DATA_PATH  = './datasets/federated_datasets_noslowite_nosqlmap/eval/'

train_loader, validation_loader, test_loader, eval_loader = load_centralized_dataset(
    TRAIN_DATA_PATH, EVAL_DATA_PATH, quiet=QUIET)

################### Training ###################
def train_centralized_model(model, train_loader, validation_loader, test_loader, quiet=True, debug=False, model_name=''):
    """
    Train a centralized model on the given dataset.
    """
    best_vloss = training_model(model, train_loader, validation_loader, quiet=quiet, debug=debug, model_name=model_name)

    # Evaluate the model on the test dataset
    test_results = evaluate_centralized_model(model, test_loader, quiet=quiet, debug=debug)
    print(f"Test Accuracy: {test_results['accuracy']:.6f}%")
    print(f"Test F1 Score (per class):\n{test_results['f1_score']['per_class']}")
    print(f"Test F1 Score (weighted): {test_results['f1_score']['weighted']:.6f}")
    print(f"Test F1 Score (macro): {test_results['f1_score']['macro']:.6f}")

    # print confusion matrix
    cm = test_results['confusion_matrix']
    print(f"Test Confusion Matrix:\n{cm}")

    return best_vloss


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
    hidden_dim = 256
    # MLP Model
    print("\n" + "="*50)
    print("Training MLP Model")
    print("="*50)
    model = MLPClassifier(input_features=PACKET_LEN, hidden_dim=hidden_dim, output_dim=NUM_CLASS)
    model.to(DEVICE)
    # Train the model
    best_vloss = train_centralized_model(model, train_loader, validation_loader, test_loader, quiet=QUIET, debug=DEBUG, model_name='MLP')
    print(f"Best Validation Loss: {best_vloss:.6f}")
    # Evaluate the model on  evaluation dataset
    eval_results = evaluate_centralized_model(model, eval_loader, quiet=QUIET, debug=DEBUG)
    print(f"Evaluation Accuracy: {eval_results['accuracy']:.6f}%")
    print(f"Evaluation F1 Score (per class):\n{eval_results['f1_score']['per_class']}")
    print(f"Evaluation F1 Score (weighted): {eval_results['f1_score']['weighted']:.6f}")
    print(f"Evaluation F1 Score (macro): {eval_results['f1_score']['macro']:.6f}")
    print(f"Evaluation Confusion Matrix:\n{eval_results['confusion_matrix']}")
    # Plot the confusion matrix with class labels
    disp = ConfusionMatrixDisplay(confusion_matrix=eval_results['confusion_matrix'], display_labels=CLASS_NAME)
    fig, ax = plt.subplots(figsize=(10, 8))
    disp.plot(ax=ax, cmap=plt.cm.Blues)
    plt.title('Eval Confusion Matrix MLP')
    plt.savefig(f'confusion_matrix_eval_MLP.png')
    plt.close()
    # Save the model
    torch.save(model.state_dict(), 'mlp_model.pth')

    # CNN Model
    print("\n" + "="*50)
    print("Training CNN Model")
    print("="*50)
    model = CNNClassifier(input_features=PACKET_LEN, output_dim=NUM_CLASS)
    model.to(DEVICE)
    # Train the model
    best_vloss = train_centralized_model(model, train_loader, validation_loader, test_loader, quiet=QUIET, debug=DEBUG, model_name='CNN')
    print(f"Best Validation Loss: {best_vloss:.6f}")
    # Evaluate the model on  evaluation dataset
    eval_results = evaluate_centralized_model(model, eval_loader, quiet=QUIET, debug=DEBUG)
    print(f"Evaluation Accuracy: {eval_results['accuracy']:.6f}%")
    print(f"Evaluation F1 Score (per class):\n{eval_results['f1_score']['per_class']}")
    print(f"Evaluation F1 Score (weighted): {eval_results['f1_score']['weighted']:.6f}")
    print(f"Evaluation F1 Score (macro): {eval_results['f1_score']['macro']:.6f}")
    print(f"Evaluation Confusion Matrix:\n{eval_results['confusion_matrix']}")
    # Plot the confusion matrix with class labels
    disp = ConfusionMatrixDisplay(confusion_matrix=eval_results['confusion_matrix'], display_labels=CLASS_NAME)
    fig, ax = plt.subplots(figsize=(10, 8))
    disp.plot(ax=ax, cmap=plt.cm.Blues)
    plt.title('Eval Confusion Matrix CNN')
    plt.savefig(f'confusion_matrix_eval_CNN.png')
    plt.close()
    # Save the model
    torch.save(model.state_dict(), 'cnn_model.pth')


    # RNN Model
    print("\n" + "="*50)
    print("Training RNN Model")
    print("="*50)
    model = RNNClassifier(input_features=PACKET_LEN, hidden_dim=hidden_dim, output_dim=NUM_CLASS)
    model.to(DEVICE)
    # Train the model
    best_vloss = train_centralized_model(model, train_loader, validation_loader, test_loader, quiet=QUIET, debug=DEBUG, model_name='RNN')
    print(f"Best Validation Loss: {best_vloss:.6f}")
    # Evaluate the model on  evaluation dataset
    eval_results = evaluate_centralized_model(model, eval_loader, quiet=QUIET, debug=DEBUG)
    print(f"Evaluation Accuracy: {eval_results['accuracy']:.6f}%")
    print(f"Evaluation F1 Score (per class):\n{eval_results['f1_score']['per_class']}")
    print(f"Evaluation F1 Score (weighted): {eval_results['f1_score']['weighted']:.6f}")
    print(f"Evaluation F1 Score (macro): {eval_results['f1_score']['macro']:.6f}")
    print(f"Evaluation Confusion Matrix:\n{eval_results['confusion_matrix']}")
    # Plot the confusion matrix with class labels
    disp = ConfusionMatrixDisplay(confusion_matrix=eval_results['confusion_matrix'], display_labels=CLASS_NAME)
    fig, ax = plt.subplots(figsize=(10, 8))
    disp.plot(ax=ax, cmap=plt.cm.Blues)
    plt.title('Eval Confusion Matrix RNN')
    plt.savefig(f'confusion_matrix_eval_RNN.png')
    plt.close()
    # Save the model
    torch.save(model.state_dict(), 'rnn_model.pth') 


    # GRU Model
    print("\n" + "="*50)
    print("Training GRU Model")
    print("="*50)
    model = GRUClassifier(input_features=PACKET_LEN, hidden_dim=hidden_dim, output_dim=NUM_CLASS)
    model.to(DEVICE)
    # Train the model
    best_vloss = train_centralized_model(model, train_loader, validation_loader, test_loader, quiet=QUIET, debug=DEBUG, model_name='GRU')
    print(f"Best Validation Loss: {best_vloss:.6f}")
    # Evaluate the model on  evaluation dataset
    eval_results = evaluate_centralized_model(model, eval_loader, quiet=QUIET, debug=DEBUG)
    print(f"Evaluation Accuracy: {eval_results['accuracy']:.6f}%")
    print(f"Evaluation F1 Score (per class):\n{eval_results['f1_score']['per_class']}")
    print(f"Evaluation F1 Score (weighted): {eval_results['f1_score']['weighted']:.6f}")
    print(f"Evaluation F1 Score (macro): {eval_results['f1_score']['macro']:.6f}")
    print(f"Evaluation Confusion Matrix:\n{eval_results['confusion_matrix']}")
    # Plot the confusion matrix with class labels
    disp = ConfusionMatrixDisplay(confusion_matrix=eval_results['confusion_matrix'], display_labels=CLASS_NAME)
    fig, ax = plt.subplots(figsize=(10, 8))
    disp.plot(ax=ax, cmap=plt.cm.Blues)
    plt.title('Eval Confusion Matrix GRU')
    plt.savefig(f'confusion_matrix_eval_GRU.png')
    plt.close()
    # Save the model
    torch.save(model.state_dict(), 'gru_model.pth')


    # LSTM Model
    print("\n" + "="*50)
    print("Training LSTM Model")
    print("="*50)
    model = LSTMClassifier(input_features=PACKET_LEN, hidden_dim=hidden_dim, output_dim=NUM_CLASS)
    model.to(DEVICE)
    # Train the model
    best_vloss = train_centralized_model(model, train_loader, validation_loader, test_loader, quiet=QUIET, debug=DEBUG, model_name='LSTM')
    print(f"Best Validation Loss: {best_vloss:.6f}")
    # Evaluate the model on  evaluation dataset
    eval_results = evaluate_centralized_model(model, eval_loader, quiet=QUIET, debug=DEBUG)
    print(f"Evaluation Accuracy: {eval_results['accuracy']:.6f}%")
    print(f"Evaluation F1 Score (per class):\n{eval_results['f1_score']['per_class']}")
    print(f"Evaluation F1 Score (weighted): {eval_results['f1_score']['weighted']:.6f}")
    print(f"Evaluation F1 Score (macro): {eval_results['f1_score']['macro']:.6f}")
    print(f"Evaluation Confusion Matrix:\n{eval_results['confusion_matrix']}")
    # Plot the confusion matrix with class labels
    disp = ConfusionMatrixDisplay(confusion_matrix=eval_results['confusion_matrix'], display_labels=CLASS_NAME)
    fig, ax = plt.subplots(figsize=(10, 8))
    disp.plot(ax=ax, cmap=plt.cm.Blues)
    plt.title('Eval Confusion Matrix LSTM')
    plt.savefig(f'confusion_matrix_eval_LSTM.png')
    plt.close()
    # Save the model
    torch.save(model.state_dict(), 'lstm_model.pth')

    # Transformer Model
    print("\n" + "="*50)
    print("Training Transformer Model")
    print("="*50)

    # Initialize the model
    model = TransformerClassifier(input_features=PACKET_LEN)
    model.to(DEVICE)

    # Train the model
    best_vloss = train_centralized_model(model, train_loader, validation_loader, test_loader, quiet=QUIET, debug=DEBUG, model_name='Transformer')
    print(f"Best Validation Loss: {best_vloss:.6f}")
    
    # Evaluate the model on the evaluation dataset
    eval_results = evaluate_centralized_model(model, eval_loader, quiet=QUIET, debug=DEBUG)
    print(f"Evaluation Accuracy: {eval_results['accuracy']:.6f}%")
    print(f"Evaluation F1 Score (per class):\n{eval_results['f1_score']['per_class']}")
    print(f"Evaluation F1 Score (weighted): {eval_results['f1_score']['weighted']:.6f}")
    print(f"Evaluation F1 Score (macro): {eval_results['f1_score']['macro']:.6f}")
    print(f"Evaluation Confusion Matrix:\n{eval_results['confusion_matrix']}")
    # Plot the confusion matrix with class labels
    disp = ConfusionMatrixDisplay(confusion_matrix=eval_results['confusion_matrix'], display_labels=CLASS_NAME)
    fig, ax = plt.subplots(figsize=(10, 8))
    disp.plot(ax=ax, cmap=plt.cm.Blues)
    plt.title('Test Confusion Matrix Transformer')
    plt.savefig(f'confusion_matrix_eval_Transformer.png')
    plt.close()
    # Save the model
    torch.save(model.state_dict(), 'transformer_model.pth')