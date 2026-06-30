import random
import torch
from torch.utils.data import DataLoader
import copy
from sklearn.metrics import confusion_matrix,classification_report,ConfusionMatrixDisplay,accuracy_score,f1_score
import matplotlib.pyplot as plt
from collections import defaultdict
from tqdm import tqdm, trange
import copy
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # reach IDS_lib in parent dir
from IDS_lib import *
import torch.nn.functional as F
import pickle

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

QUIET = False
DEBUG = False

# Data file path
# TRAIN_DATA_PATH = './datasets/federated_datasets_noslowite/train/'
# EVAL_DATA_PATH = './datasets/federated_datasets_noslowite/eval/'

TRAIN_DATA_PATH = '/home/linhngn/newsetup/IDS_NWDAF_DL_Research/datasets/overlapping_federated_datasets/train/'
EVAL_DATA_PATH  = '/home/linhngn/newsetup/IDS_NWDAF_DL_Research/datasets/overlapping_federated_datasets/eval/'

# Federated Learning CONST param
FD_DELTA_ACC = 0.01 # Minimum accuracy improvement to continue training
FD_PATIENCE = 5
ROUNDS = 100 # number of rounds for federated learning
TEACHER_TEMPERATURE = 1 # Temperature for soft labels

public_dataloaders, train_loaders, validation_loaders, test_loaders, eval_loader = load_public_and_private_datasets(
    TRAIN_DATA_PATH, EVAL_DATA_PATH, quiet=QUIET)

# use the first dataset as public dataset
public_train_dataloader = public_dataloaders['train']
public_validation_dataloader = public_dataloaders['validation']
# public_test_dataloader = public_dataloaders['test']
public_dataloaders = {
    'train': copy.deepcopy(public_train_dataloader),
    'validation': copy.deepcopy(public_validation_dataloader)
    # 'test': copy.deepcopy(public_test_dataloader) 
}
public_dataloaders_true_label = {
    'train': public_train_dataloader,
    'validation': public_validation_dataloader
    # 'test': public_test_dataloader 
}
# convert true labels to one-hot
public_dataloaders_true_label['train'].dataset.set_soft_labels(
    F.one_hot(public_dataloaders_true_label['train'].dataset.get_Y_tensor(), num_classes=NUM_CLASS).float())
public_dataloaders_true_label['validation'].dataset.set_soft_labels(
    F.one_hot(public_dataloaders_true_label['validation'].dataset.get_Y_tensor(), num_classes=NUM_CLASS).float())


################# Federated Distillation #################


def run_federated_distillation(model_list, public_dataloaders, train_loaders, validation_loaders, test_loaders, 
                          rounds=ROUNDS, fl_patience = FD_PATIENCE ,quiet=True, debug=False, model_name=""):
    """Run the federated learning process with multiple regions"""
    # Data structures before federated learning loop
    round_metrics = {
        # overall metrics
        'avg_models_accuracy': [],  # Average accuracy of all models per round
        'avg_models_f1_weighted': [],  # Average weighted F1 score of all models per round
        'avg_models_f1_macro': [],  # Average macro F1 score of all models per round
        # metrics for each model
        'global_accuracy': defaultdict(list),  # Global model accuracy per round
        'avg_region_accuracy': defaultdict(list),  # Average regional accuracy per round
        'global_f1_weighted': defaultdict(list),  # Global weighted F1 score
        'avg_region_f1_weighted': defaultdict(list),  # Average regional weighted F1 score
        'global_f1_macro': defaultdict(list),  # Global macro F1 score
        'avg_region_f1_macro': defaultdict(list),  # Average regional macro F1 score
        # Add metrics for public dataset performance
        'avg_public_accuracy': [],  # Average accuracy on public dataset
        'public_accuracy': defaultdict(list),  # Models accuracy on public data
        'public_f1_weighted': defaultdict(list),  # Weighted F1 score on public data
        'public_f1_macro': defaultdict(list),  # Macro F1 score on public data
    }

    patience_counter = 0

    round_pbar = trange(rounds, desc="Federated Distillation Rounds",leave=not quiet) 
    # Federated Distillation loop
    for round in round_pbar:
        # Train n models on public dataset
        for model_idx,model in enumerate(model_list):
            best_vloss= distillation_training_model(model,public_dataloaders_true_label['train'], public_dataloaders['train'], public_dataloaders_true_label['validation'], public_dataloaders['validation'], 
                                     patience=5, min_delta=DELTA_LOSS, quiet=quiet, debug=debug, model_name=f"{model_name}_{model_idx}_distillation")
        # Train n models on n private regional datasets
        for model_idx,model in enumerate(model_list):
            best_vloss= training_model(model, train_loaders[model_idx], validation_loaders[model_idx], 
                                     patience=5, min_delta=DELTA_LOSS, quiet=quiet, debug=debug, model_name=f"{model_name}_{model_idx}_private")

        softlabel_train=[]
        softlabel_validation=[]
        # softlabel_test=[]

        with torch.no_grad():
            #  Use the models on public dataset
            for model_idx,model in enumerate(model_list):
                model.train(False)
                model.eval()
                # Evaluate the model on the public dataset
                logit_train = model(public_dataloaders['train'].dataset.get_X_tensor())
                logit_validation = model(public_dataloaders['validation'].dataset.get_X_tensor())
                # logit_test = model(public_dataset['test'].dataset.get_X_tensor())
                # softlabel_train.append(torch.softmax(logit_train/TEACHER_TEMPERATURE, dim=-1))
                # softlabel_validation.append(torch.softmax(logit_validation/TEACHER_TEMPERATURE, dim=-1))
                softlabel_train.append(logit_train)
                softlabel_validation.append(logit_validation)
                # Use the logits as soft labels
                # softlabel_train.append(logit_train)
                # softlabel_validation.append(logit_validation)
                # softlabel_test.append(logit_test)
        
        # Get the true one-hot encoded labels
        true_labels_train = public_dataloaders_true_label['train'].dataset.get_Y_tensor()
        true_labels_validation = public_dataloaders_true_label['validation'].dataset.get_Y_tensor()

        # Create tensors to store the weighted soft labels
        weighted_softlabel_train = torch.zeros_like(softlabel_train[0])
        weighted_softlabel_validation = torch.zeros_like(softlabel_validation[0])

        # Process each sample individually
        num_samples_train = softlabel_train[0].size(0)
        num_samples_validation = softlabel_validation[0].size(0)
        
        # For training samples
        for sample_idx in range(num_samples_train):
            # Get predictions and true label for this sample
            sample_preds = [model_pred[sample_idx] for model_pred in softlabel_train]
            true_label = true_labels_train[sample_idx]
            
            # Calculate similarity for each model's prediction for this sample
            similarities = []
            for pred in sample_preds:
                # one sample is one sequence of packets, so we need to calculate loss for each packet in the sequence
                # Calculate cross-entropy loss for each packet
                loss = F.cross_entropy(pred, true_label,reduction='none')
                # Convert loss to similarity (higher for better predictions)
                similarity = 1.0 / (loss + 1e-5)
                similarities.append(similarity)
            
            # Convert similarities to weights
            similarities = torch.stack(similarities, dim=0)  # Shape: (num_models, num_packets)
            weights = F.softmax(similarities/2, dim=0)
            weights = weights.unsqueeze(-1)  # Shape: (num_models, num_packets, 1)
            # Create weighted prediction for this sample
            for i, pred in enumerate(sample_preds):
                # For each packet in the sequence, we add the weighted prediction
                weighted_softlabel_train[sample_idx] += weights[i] * pred
        
        # For validation samples - same process
        for sample_idx in range(num_samples_validation):
            # Get predictions and true label for this sample
            sample_preds = [model_pred[sample_idx] for model_pred in softlabel_validation]
            true_label = true_labels_validation[sample_idx]
            
            # Calculate similarity for each model's prediction for this sample
            similarities = []
            for pred in sample_preds:
                # Calculate cross-entropy loss for each packet in the sequence
                loss = F.cross_entropy(pred, true_label, reduction='none')
                # Convert loss to similarity (higher for better predictions)
                similarity = 1.0 / (loss + 1e-5)
                similarities.append(similarity)
            
            # Convert similarities to weights
            similarities = torch.stack(similarities)  # Shape: (num_models, num_packets)
            weights = F.softmax(similarities/2, dim=0)
            weights = weights.unsqueeze(-1)  # Shape: (num_models, num_packets, 1)
            
            # Create weighted prediction for this sample
            for i, pred in enumerate(sample_preds):
                # For each packet in the sequence, we add the weighted prediction
                weighted_softlabel_validation[sample_idx] += weights[i] * pred
        
        # Replace the simple averaging with weighted averaging
        avg_softlabel_train = torch.softmax(weighted_softlabel_train/TEACHER_TEMPERATURE, dim=-1)
        avg_softlabel_validation = torch.softmax(weighted_softlabel_validation/TEACHER_TEMPERATURE,dim=-1)

        # Average all the logits
        # avg_softlabel_train = torch.mean(torch.stack(softlabel_train), dim=0) 
        # avg_softlabel_validation = torch.mean(torch.stack(softlabel_validation), dim=0) 
        # avg_softlabel_test = torch.mean(torch.stack(softlabel_test), dim=0)

        # Use the averaged logits as soft labels
        public_dataloaders['train'].dataset.set_soft_labels(avg_softlabel_train)
        public_dataloaders['validation'].dataset.set_soft_labels(avg_softlabel_validation)
        # public_dataset['test'].dataset.set_soft_labels(avg_softlabel_test)
        
        avg_models_accuracy = 0
        avg_models_f1_weighted = 0
        avg_models_f1_macro = 0
        avg_public_accuracy = 0

        # Validate each model with all validation public data and all validation private data and collect detailed metrics
        for model_idx,model in enumerate(model_list):
            all_predictions = []
            all_labels = []
            
            # Evaluate the model on the public validation dataset
            public_validation_results = evaluate_model(model, [public_dataloaders_true_label['validation']], quiet=quiet, debug=debug)
            
            # Process public validation results first
            public_result = public_validation_results[0]
            public_accuracy = public_result['accuracy']
            avg_public_accuracy += public_accuracy

            if NUM_CLASS == 2:  # Binary classification
                public_f1_weighted = public_f1_macro = public_result['f1_score']
            else:  # Multiclass
                public_f1_weighted = public_result['f1_score']['weighted']
                public_f1_macro = public_result['f1_score']['macro']
            # Add public metrics to round metrics
            round_metrics['public_accuracy'][model_idx].append(public_accuracy)
            round_metrics['public_f1_weighted'][model_idx].append(public_f1_weighted)
            round_metrics['public_f1_macro'][model_idx].append(public_f1_macro)
            
            all_predictions.extend(public_result['predictions'])
            all_labels.extend(public_result['labels'])

            # Evaluate the model on the private validation dataset
            all_region_results = evaluate_model(model, test_loaders, quiet=quiet, debug=debug)

            # Process regional validation results
            num_regions = len(validation_loaders)

            avg_region_accuracy = 0
            avg_region_f1_weighted = 0
            avg_region_f1_macro = 0

            for region_id, results in all_region_results.items():
                # Extract and store regional metrics
                accuracy = results['accuracy']
                avg_region_accuracy += accuracy
                
                if NUM_CLASS == 2:  # Binary classification
                    f1 = results['f1_score']
                    avg_region_f1_weighted += f1
                    avg_region_f1_macro += f1
                else:  # Multiclass
                    f1_weighted = results['f1_score']['weighted']
                    f1_macro = results['f1_score']['macro']
                    avg_region_f1_weighted += f1_weighted
                    avg_region_f1_macro += f1_macro
                
                # Collect all predictions and labels across regions for averaging metrics
                all_predictions.extend(results['predictions'])
                all_labels.extend(results['labels'])

            # Add metrics to the round metrics dictionary
            round_metrics['avg_region_accuracy'][model_idx].append(avg_region_accuracy / num_regions)
            round_metrics['avg_region_f1_weighted'][model_idx].append(avg_region_f1_weighted / num_regions)
            round_metrics['avg_region_f1_macro'][model_idx].append(avg_region_f1_macro / num_regions)

            # Calculate true global metrics based on all predictions across regions
            global_accuracy = 100 * accuracy_score(all_labels, all_predictions)
            avg_models_accuracy += global_accuracy
        
            if NUM_CLASS == 2:  # Binary classification
                global_f1 = f1_score(all_labels, all_predictions)
                global_f1_weighted = global_f1
                global_f1_macro = global_f1
            else:  # Multiclass
                global_f1_weighted = f1_score(all_labels, all_predictions, average='weighted')
                global_f1_macro = f1_score(all_labels, all_predictions, average='macro')

            avg_models_f1_weighted += global_f1_weighted
            avg_models_f1_macro += global_f1_macro
        
            round_metrics['global_accuracy'][model_idx].append(global_accuracy)
            round_metrics['global_f1_weighted'][model_idx].append(global_f1_weighted)
            round_metrics['global_f1_macro'][model_idx].append(global_f1_macro)

        # Calculate average metrics across all models
        avg_public_accuracy /= len(model_list)
        round_metrics['avg_public_accuracy'].append(avg_public_accuracy)
        avg_models_accuracy /= len(model_list)
        avg_models_f1_weighted /= len(model_list)
        avg_models_f1_macro /= len(model_list)
        round_metrics['avg_models_accuracy'].append(avg_models_accuracy)
        round_metrics['avg_models_f1_weighted'].append(avg_models_f1_weighted)
        round_metrics['avg_models_f1_macro'].append(avg_models_f1_macro)

        # Check for convergence
        if round >= 1:
            acc_improvement = round_metrics['avg_models_accuracy'][-1] - round_metrics['avg_models_accuracy'][-2]
            if not quiet:
                round_pbar.set_postfix({
                    'Avg_Mdl_Acc': f"{avg_models_accuracy:.2f}%", 
                    'Avg_Mdl_F1': f"{avg_models_f1_weighted:.4f}",
                    'Avg_Pub_Acc': f"{avg_public_accuracy:.2f}%",
                })
            
            # Optional: Early stopping based on convergence criteria
            if abs(acc_improvement) < FD_DELTA_ACC:
                if debug:
                    print(f"Convergence detected after {round+1} rounds!")
                patience_counter += 1
                if patience_counter >= fl_patience:
                    if debug:
                        print(f"Convergence sustained for {fl_patience} rounds! Stopping early.")
                    break
            else:
                patience_counter = 0  # Reset patience counter if improvement is significant
            
    return round_metrics

################# Evaluation #################

# Function for detailed model evaluation
def evaluate_model(model, test_loaders, quiet=True, debug=False):
    """Evaluate model on test data from all regions"""
        
    results = {}
    model.eval()
    
    for i in range(len(test_loaders)):
        correct = 0
        total = 0
        all_preds = []
        all_labels = []
        
        with torch.no_grad():
            for data in test_loaders[i]:
                inputs, labels = data
                outputs = model(inputs)
                predicted = torch.argmax(outputs.data, 2)
                # If labels are one-hot encoded, convert them to class indices
                if labels.dim() > 2 and labels.shape[-1] == NUM_CLASS:
                    labels = torch.argmax(labels, 2)
                
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
        
        results[i] = {
            'total': total,
            'correct': correct,
            'accuracy': accuracy,
            'f1_score': f1,
            'predictions': all_preds,
            'labels': all_labels
        }
    
    return results

################# Plotting Function #################
# Function to visualize convergence
def plot_progress(round_metrics, image_path='convergence_plots.png'):
    """Plot convergence metrics across rounds
        # Data structures before federated learning loop
        round_metrics = {
            # overall metrics
            'avg_models_accuracy': [],  # Average accuracy of all models per round
            'avg_models_f1_weighted': [],  # Average weighted F1 score of all models per round
            'avg_models_f1_macro': [],  # Average macro F1 score of all models per round
            # metrics for each model
            'global_accuracy': defaultdict(list),  # Global model accuracy per round
            'avg_region_accuracy': defaultdict(list),  # Average regional accuracy per round
            'global_f1_weighted': defaultdict(list),  # Global weighted F1 score
            'avg_region_f1_weighted': defaultdict(list),  # Average regional weighted F1 score
            'global_f1_macro': defaultdict(list),  # Global macro F1 score
            'avg_region_f1_macro': defaultdict(list),  # Average regional macro F1 score
            # Add metrics for public dataset performance
            'avg_public_accuracy': [],  # Average accuracy on public dataset
            'public_accuracy': defaultdict(list),  # Models accuracy on public data
            'public_f1_weighted': defaultdict(list),  # Weighted F1 score on public data
            'public_f1_macro': defaultdict(list),  # Macro F1 score on public data
        }
    """
    rounds = list(range(1, len(round_metrics['avg_models_accuracy']) + 1))
    
    plt.figure(figsize=(15, 15))  # Larger figure to accommodate additional plots
    
    # Plot 1: Average accuracy over all models
    plt.subplot(3, 2, 1)
    plt.plot(rounds, round_metrics['avg_models_accuracy'], label='Average Model Accuracy')
    plt.plot(rounds, round_metrics['avg_public_accuracy'], label='Average Public dataset Accuracy')
    plt.title('Accuracy Across Rounds')
    plt.xlabel('Round')
    plt.ylabel('Accuracy (%)')
    plt.legend()
    plt.grid(True)
    
    # Plot 2: Average F1 scores over all models (weighted and macro)
    plt.subplot(3, 2, 2)
    plt.plot(rounds, round_metrics['avg_models_f1_weighted'], label='Average Model Weighted F1 Score')
    plt.plot(rounds, round_metrics['avg_models_f1_macro'], label='Average Model Macro F1 Score')
    plt.title('F1 Scores Across Rounds')
    plt.xlabel('Round')
    plt.ylabel('F1 Score')
    plt.legend()
    plt.grid(True)

    # Plot 3: Public dataset accuracies of each model
    plt.subplot(3, 2, 3)
    for model_idx in range(len(round_metrics['public_accuracy'])):
        plt.plot(rounds, round_metrics['public_accuracy'][model_idx], label=f'Model {model_idx}')
    plt.title('Public Dataset Accuracies Across Rounds')
    plt.xlabel('Round')
    plt.ylabel('Accuracy (%)')
    plt.legend()
    plt.grid(True)

    # Plot 4: Average F1 scores of each model on public dataset
    plt.subplot(3, 2, 4)
    for model_idx in range(len(round_metrics['public_f1_weighted'])):
        plt.plot(rounds, round_metrics['public_f1_weighted'][model_idx], label=f'Model {model_idx}')
    plt.title('Public Dataset F1 Scores Across Rounds')
    plt.xlabel('Round')
    plt.ylabel('F1 Score')
    plt.legend()
    plt.grid(True)

    # Plot 5: Global accuracies of each model on all regions's private datasets
    plt.subplot(3, 2, 5)
    for model_idx in range(len(round_metrics['global_accuracy'])):
        plt.plot(rounds, round_metrics['global_accuracy'][model_idx], label=f'Model {model_idx}')
    plt.title('Global Accuracies on all private datasets Across Rounds')
    plt.xlabel('Round')
    plt.ylabel('Accuracy (%)')
    plt.legend()
    plt.grid(True)

    # Plot 6: F1 scores of each model on all regions's private datasets
    plt.subplot(3, 2, 6)
    for model_idx in range(len(round_metrics['global_f1_weighted'])):
        plt.plot(rounds, round_metrics['global_f1_weighted'][model_idx], label=f'Model {model_idx}')
    plt.title('Global F1 Scores on all private datasets Across Rounds')
    plt.xlabel('Round')
    plt.ylabel('F1 Score')
    plt.legend()
    plt.grid(True)
    
    
    # Adjust layout to prevent overlap
    plt.tight_layout()
    plt.savefig(image_path)
    # plt.show()

################ Printing Results #################
def print_results(eval_results, cmfig_title="Confusion Matrix", cmfig_filename="confusion_matrix.png"):
    """Print evaluation results for all regions and calculate global metrics."""
    avg_region_accuracy = 0
    avg_region_f1_weighted = 0
    avg_region_f1_macro = 0
    all_predictions = []
    all_labels = []
    
    # Process each region's results
    num_datasets = len(eval_results)
    print("-"*50)
    print(f"Results across {num_datasets} region datasets:")
    
    for result_id, metrics in eval_results.items():
        # Extract regional metrics
        accuracy = metrics['accuracy']
        avg_region_accuracy += accuracy
        
        # Collect all predictions and labels for global metrics
        all_predictions.extend(metrics['predictions'])
        all_labels.extend(metrics['labels'])
        
        # Print region-specific results based on classification type
        if NUM_CLASS == 2:  # Binary classification
            f1 = metrics['f1_score']
            avg_region_f1_weighted += f1
            avg_region_f1_macro += f1
            print(f"Region {result_id} - Accuracy: {accuracy:.2f}% - F1 Score: {f1:.4f}")
        else:  # Multi-class classification
            f1_weighted = metrics['f1_score']['weighted']
            f1_macro = metrics['f1_score']['macro']
            avg_region_f1_weighted += f1_weighted
            avg_region_f1_macro += f1_macro
            print(f"Region {result_id} - Accuracy: {accuracy:.2f}% - F1 Score (Weighted): {f1_weighted:.4f}")

    # Calculate average regional metrics
    avg_region_accuracy /= num_datasets
    avg_region_f1_weighted /= num_datasets
    avg_region_f1_macro /= num_datasets
    
    # Print average regional metrics
    print("Average Regional Metrics:")
    if NUM_CLASS == 2:
        print(f"Accuracy: {avg_region_accuracy:.2f}% - F1 Score: {avg_region_f1_weighted:.4f}")
    else:
        print(f"Accuracy: {avg_region_accuracy:.2f}% - F1 Score (Weighted): {avg_region_f1_weighted:.4f}")

    # Calculate true global metrics based on all predictions across regions
    global_accuracy = 100 * accuracy_score(all_labels, all_predictions)

    # Print global metrics
    print("Global Metrics (all regions combined):")
    if NUM_CLASS == 2:  # Binary classification
        global_f1 = f1_score(all_labels, all_predictions)
        print(f"Accuracy: {global_accuracy:.2f}% - F1 Score: {global_f1:.4f}")
    else:  # Multi-class classification
        global_f1_weighted = f1_score(all_labels, all_predictions, average='weighted')
        global_f1_macro = f1_score(all_labels, all_predictions, average='macro')
        global_f1_per_class = f1_score(all_labels, all_predictions, average=None)
        print(f"Accuracy: {global_accuracy:.2f}% - F1 Score (Weighted): {global_f1_weighted:.4f} - F1 Score (Macro): {global_f1_macro:.4f}")
        print(f"F1 Score per class: {global_f1_per_class}")
        
    if num_datasets == 1:
        # For single region, plot confusion matrix
        cm = confusion_matrix(all_labels, all_predictions)
        disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=CLASS_NAME)
        fig = plt.figure(figsize=(10, 8))
        disp.plot(ax=fig.gca(), cmap=plt.cm.Blues)
        plt.title(cmfig_title)
        plt.savefig(cmfig_filename)
        # plt.show()
        plt.close('all')  # Close the plot to free memory
    print("-"*50)

################# Main Script #################

# Modify the main federated training section to use the new function
if __name__ == "__main__":
    # R4-8: FedDistill Transformer on the OVERLAPPING-skewed split (faithful copy of the
    # original pipeline; only the dataset path, architecture scope and output dir changed).
    OUTDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "r48_fd")
    os.makedirs(OUTDIR, exist_ok=True)
    print("="*50 + "\nFedDistill Transformer on OVERLAPPING split\n" + "="*50, flush=True)
    transformer_model_list = []
    for i in range(NUM_REGION):
        m = TransformerClassifier(input_features=PACKET_LEN)
        m.to(DEVICE)
        transformer_model_list.append(m)
    rm = run_federated_distillation(
        transformer_model_list, public_dataloaders, train_loaders, validation_loaders,
        test_loaders, rounds=ROUNDS, quiet=True, debug=False, model_name="Transformer")
    pickle.dump(rm, open(os.path.join(OUTDIR, "round_metrics_FD_Transformer.pkl"), "wb"))
    all_test = [evaluate_model(m, test_loaders, quiet=True) for m in transformer_model_list]
    all_eval = [evaluate_model(m, [eval_loader], quiet=True) for m in transformer_model_list]
    pickle.dump(all_test, open(os.path.join(OUTDIR, "private_test_results_FD_Transformer.pkl"), "wb"))
    pickle.dump(all_eval, open(os.path.join(OUTDIR, "evaluation_results_FD_Transformer.pkl"), "wb"))
    for i, m in enumerate(transformer_model_list):
        torch.save(m.state_dict(), os.path.join(OUTDIR, f"model_FD_Transformer_{i+1}.pth"))
    from sklearn.metrics import accuracy_score, f1_score
    accs = [accuracy_score(e[0]["labels"], e[0]["predictions"]) * 100 for e in all_eval]
    f1s = [f1_score(e[0]["labels"], e[0]["predictions"], average="weighted", zero_division=0) * 100 for e in all_eval]
    print("OVERLAP FedDistill Transformer eval regional acc:", [f"{a:.2f}" for a in accs],
          "mean_acc=%.2f mean_f1w=%.2f" % (sum(accs)/len(accs), sum(f1s)/len(f1s)), flush=True)
