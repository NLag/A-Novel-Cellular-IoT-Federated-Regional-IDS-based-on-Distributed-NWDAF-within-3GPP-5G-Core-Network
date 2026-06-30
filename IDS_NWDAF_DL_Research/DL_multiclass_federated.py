import torch
from torch.utils.data import DataLoader
import copy
from sklearn.metrics import confusion_matrix,classification_report,ConfusionMatrixDisplay,accuracy_score,f1_score
import matplotlib.pyplot as plt
from collections import defaultdict
from tqdm import tqdm, trange
import concurrent.futures
import os
import pickle

from IDS_lib import *

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

QUIET = False
DEBUG = False

# Data file path
# TRAIN_DATA_PATH = './datasets/simple_federated_datasets/train/'
# EVAL_DATA_PATH = './datasets/simple_federated_datasets/eval/'

TRAIN_DATA_PATH = './datasets/federated_datasets_noslowite_nosqlmap/train/'
EVAL_DATA_PATH  = './datasets/federated_datasets_noslowite_nosqlmap/eval/'

# Federated Learning CONST param
FL_DELTA_ACC = 0.01
FL_DELTA_WEIGHT = 0.0001
FL_PATIENCE = 5
ROUNDS = 50

if __name__ == "__main__":
    train_loaders, validation_loaders, test_loaders, eval_loader = load_private_region_datasets(
        TRAIN_DATA_PATH, EVAL_DATA_PATH, quiet=QUIET)

################# Federated Training #################

def run_federated_learning(model_list, train_loaders, validation_loaders, test_loaders, 
                          rounds=ROUNDS, fl_patience = FL_PATIENCE ,quiet=True, debug=False, model_name=""):
    """Run the federated learning process with multiple regions"""
    # Data structures before federated learning loop
    round_metrics = {
        'global_accuracy': [],  # Global model accuracy per round
        'avg_region_accuracy': [],  # Average regional accuracy per round
        'local_accuracies': defaultdict(list),  # Regional accuracies per round
        'global_f1_weighted': [],  # Global weighted F1 score
        'avg_region_f1_weighted': [],  # Average regional weighted F1 score
        'global_f1_macro': [],  # Global macro F1 score
        'avg_region_f1_macro': [],  # Average regional macro F1 score
        'local_f1_weighted': defaultdict(list),  # Regional weighted F1 scores
        'local_f1_macro': defaultdict(list),  # Regional macro F1 scores
        'weight_changes': [],  # Magnitude of weight changes between rounds
        'global_f1_per_class': []  # Global F1 score per class (for multiclass)
    }

    prev_state_dict = None
    patience_counter = 0
    averaged_model = copy.deepcopy(model_list[0])  # Use the first model as a template
    averaged_model.to(DEVICE)

    round_pbar = trange(rounds, desc="Federated Learning Rounds",leave=not quiet) 

    # Federated learning loop
    for round in round_pbar:
        # Train n models on n regions
        for i in range(len(model_list)):
            model = model_list[i]
            best_vloss= training_model(model, train_loaders[i], validation_loaders[i], 
                                     patience=5, quiet=quiet, debug=debug, model_name=f"{model_name}_{i}")

        # Average the model weights
        avg_state_dict = average_model_weights(model_list) # note: avg_state_dict is a new object

        # Calculate weight change from previous round
        weight_change = calculate_weight_change(prev_state_dict, avg_state_dict) # note: prev_state_dict and avg_state_dict must be different objects
        round_metrics['weight_changes'].append(weight_change)
        prev_state_dict = avg_state_dict # Update for next round

        # Load the averaged weights into the average model
        averaged_model.load_state_dict(avg_state_dict)
        
        # Validation the averaged model and collect detailed metrics
        all_region_results = evaluate_model(averaged_model, validation_loaders, quiet=quiet, debug=debug)

        avg_region_accuracy = 0
        avg_region_f1_weighted = 0
        avg_region_f1_macro = 0
        global_accuracy = 0
        global_f1_weighted = 0
        global_f1_macro = 0
        all_predictions = []
        all_labels = []

        # validation on each region
        num_regions = len(validation_loaders)
        for i in range(num_regions):
            results = all_region_results[i]
            # Extract and store regional metrics
            accuracy = results['accuracy']
            round_metrics['local_accuracies'][i].append(accuracy)
            avg_region_accuracy += accuracy
            
            if NUM_CLASS == 2:  # Binary classification
                f1 = results['f1_score']
                round_metrics['local_f1_weighted'][i].append(f1)
                round_metrics['local_f1_macro'][i].append(f1)
                avg_region_f1_weighted += f1
                avg_region_f1_macro += f1
            else:  # Multiclass
                f1_weighted = results['f1_score']['weighted']
                f1_macro = results['f1_score']['macro']
                round_metrics['local_f1_weighted'][i].append(f1_weighted)
                round_metrics['local_f1_macro'][i].append(f1_macro)
                avg_region_f1_weighted += f1_weighted
                avg_region_f1_macro += f1_macro
            
            # Collect all predictions and labels across regions for global metrics
            # Extend with data from other regions
            all_predictions.extend(results['predictions'])
            all_labels.extend(results['labels'])

        # After the loop over regions, we'll calculate true global metrics

        # Calculate true global metrics based on all predictions across regions
        global_accuracy = 100 * accuracy_score(all_labels, all_predictions)
        
        if NUM_CLASS == 2:  # Binary classification
            global_f1 = f1_score(all_labels, all_predictions)
            global_f1_weighted = global_f1
            global_f1_macro = global_f1
        else:  # Multiclass
            global_f1_weighted = f1_score(all_labels, all_predictions, average='weighted')
            global_f1_macro = f1_score(all_labels, all_predictions, average='macro')
            global_f1_per_class = f1_score(all_labels, all_predictions, average=None)
        
        # Add true global metrics to the round metrics
        round_metrics['avg_region_accuracy'].append(avg_region_accuracy / num_regions)
        round_metrics['avg_region_f1_weighted'].append(avg_region_f1_weighted / num_regions)
        round_metrics['avg_region_f1_macro'].append(avg_region_f1_macro / num_regions)
        round_metrics['global_accuracy'].append(global_accuracy)
        round_metrics['global_f1_weighted'].append(global_f1_weighted)
        round_metrics['global_f1_macro'].append(global_f1_macro)
        if NUM_CLASS != 2:
            round_metrics['global_f1_per_class'].append(global_f1_per_class)

        # Update all local models with the averaged weights
        for i in range(len(model_list)):
            model_list[i].load_state_dict(avg_state_dict)

        # Check for convergence
        if round >= 1:
            acc_improvement = round_metrics['global_accuracy'][-1] - round_metrics['global_accuracy'][-2]
            weight_change = round_metrics['weight_changes'][-1]
            if not quiet:
                # print(f"\nGlobal accuracy: {global_accuracy:.4f}%, Global weighted F1: {global_f1_weighted:.4f}, Weight change: {weight_change:.6f}")
                round_pbar.set_postfix({'Glb_Acc': f"{global_accuracy:.4f}%", 'Global_F1':f"{global_f1_weighted:.4f}", 'd_W': f"{weight_change:.6f}"})
            
            # Optional: Early stopping based on convergence criteria
            if acc_improvement < FL_DELTA_ACC and weight_change < FL_DELTA_WEIGHT:
                if debug:
                    print(f"Convergence detected after {round+1} rounds!")
                patience_counter += 1
                if patience_counter >= fl_patience:
                    if debug:
                        print(f"Convergence sustained for {fl_patience} rounds! Stopping early.")
                    break
            
    return round_metrics, averaged_model

################# Evaluation #################

# Function for detailed model evaluation
def evaluate_model(model, test_loaders, region_ids=None, quiet=True, debug=False):
    """Evaluate model on test data from all regions"""
    if region_ids is None:
        region_ids = range(len(test_loaders))
        
    results = {}
    model.eval()
    
    for i in region_ids:
        correct = 0
        total = 0
        all_preds = []
        all_labels = []
        
        with torch.no_grad():
            for data in test_loaders[i]:
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
def plot_convergence(round_metrics, image_path='convergence_plots.png'):
    """Plot convergence metrics across rounds"""
    rounds = list(range(1, len(round_metrics['global_accuracy']) + 1))
    
    plt.figure(figsize=(15, 15))  # Larger figure to accommodate additional plots
    
    # Plot 1: Accuracy
    plt.subplot(3, 2, 1)
    plt.plot(rounds, round_metrics['global_accuracy'], label='Global Model')
    plt.plot(rounds, round_metrics['avg_region_accuracy'], label='Average Regional')
    plt.title('Accuracy Across Rounds')
    plt.xlabel('Round')
    plt.ylabel('Accuracy (%)')
    plt.legend()
    plt.grid(True)
    
    # Plot 2: Regional accuracies
    plt.subplot(3, 2, 2)
    for region, accuracies in round_metrics['local_accuracies'].items():
        plt.plot(rounds, accuracies, label=f'Region {region}')
    plt.title('Regional Accuracies Across Rounds')
    plt.xlabel('Round')
    plt.ylabel('Accuracy (%)')
    plt.legend()
    plt.grid(True)
    
    # Plot 3: F1 scores
    plt.subplot(3, 2, 3)
    if 'global_f1_weighted' in round_metrics:
        plt.plot(rounds, round_metrics['global_f1_weighted'], label='Weighted')
    if 'global_f1_macro' in round_metrics:
        plt.plot(rounds, round_metrics['global_f1_macro'], label='Macro')
    if 'avg_region_f1_weighted' in round_metrics:
        plt.plot(rounds, round_metrics['avg_region_f1_weighted'], label='Avg Weighted')
    if 'avg_region_f1_macro' in round_metrics:
        plt.plot(rounds, round_metrics['avg_region_f1_macro'], label='Avg Macro')
    plt.title('F1 Scores Across Rounds')
    plt.xlabel('Round')
    plt.ylabel('F1 Score')
    plt.legend()
    plt.grid(True)
    
    # Plot 4: Regional F1 scores (weighted)
    plt.subplot(3, 2, 4)
    if 'local_f1_weighted' in round_metrics:
        for region, f1_scores in round_metrics['local_f1_weighted'].items():
            plt.plot(rounds, f1_scores, label=f'Region {region}')
        plt.title('Regional F1 Scores (Weighted) Across Rounds')
        plt.xlabel('Round')
        plt.ylabel('F1 Score')
        plt.legend()
        plt.grid(True)
    
    # Plot 5: Weight changes
    plt.subplot(3, 2, 5)
    plt.plot(rounds[1:], round_metrics['weight_changes'][1:])
    plt.title('Weight Changes Between Rounds')
    plt.xlabel('Round')
    plt.ylabel('Average Weight Change')
    plt.grid(True)
    
    # Plot 6: Convergence rate (change in accuracy)
    plt.subplot(3, 2, 6)
    global_acc_changes = [round_metrics['global_accuracy'][i] - round_metrics['global_accuracy'][i-1] for i in range(1, len(round_metrics['global_accuracy']))]
    avg_acc_changes = [round_metrics['avg_region_accuracy'][i] - round_metrics['avg_region_accuracy'][i-1] for i in range(1, len(round_metrics['avg_region_accuracy']))]
    plt.plot(rounds[1:], global_acc_changes)
    plt.plot(rounds[1:], avg_acc_changes)
    plt.title('Change in Accuracy Between Rounds')
    plt.xlabel('Round')
    plt.ylabel('Accuracy Change (%)')
    plt.grid(True)
    
    plt.tight_layout()
    plt.savefig(image_path)

################ Printing Results #################

def print_results(eval_results, cmfig_title="Confusion Matrix", cmfig_filename="confusion_matrix.png"):

    avg_region_accuracy = 0
    avg_region_f1_weighted = 0
    avg_region_f1_macro = 0
    global_accuracy = 0
    global_f1_weighted = 0
    global_f1_macro = 0
    all_predictions = []
    all_labels = []
    
    # test on each region
    # num_regions = NUM_REGION
    num_regions = len(eval_results)
    for region_id, metrics in eval_results.items():
        # Extract regional metrics
        accuracy = metrics['accuracy']
        avg_region_accuracy += accuracy
        if NUM_CLASS == 2:
            print(f"Region {region_id} - Accuracy: {metrics['accuracy']:.4f}% - F1 Score: {metrics['f1_score']:.4f}")
            f1 = metrics['f1_score']
            avg_region_f1_weighted += f1
            avg_region_f1_macro += f1
        else:
            print(f"Region {region_id} - Accuracy: {metrics['accuracy']:.4f}% - F1 Score (Weighted): {metrics['f1_score']['weighted']:.4f} - F1 Score (Macro): {metrics['f1_score']['macro']:.4f}")
            f1_weighted = metrics['f1_score']['weighted']
            f1_macro = metrics['f1_score']['macro']
            avg_region_f1_weighted += f1_weighted
            avg_region_f1_macro += f1_macro
        
        # Collect all predictions and labels across regions for global metrics
        # Extend with data from other regions
        all_predictions.extend(metrics['predictions'])
        all_labels.extend(metrics['labels'])

    # Calculate average regional metrics
    avg_region_accuracy /= num_regions
    avg_region_f1_weighted /= num_regions
    avg_region_f1_macro /= num_regions
    if NUM_CLASS == 2:
        print(f"Average Regional: Accuracy: {avg_region_accuracy:.4f}% - F1 Score: {avg_region_f1_weighted:.4f}")
    else:
        print(f"Average Regional: Accuracy: {avg_region_accuracy:.4f}% - F1 Score (Weighted): {avg_region_f1_weighted:.4f} - F1 Score (Macro): {avg_region_f1_macro:.4f}")

    # Calculate true global metrics based on all predictions across regions
    global_accuracy = 100 * accuracy_score(all_labels, all_predictions)

    if NUM_CLASS == 2:  # Binary classification
        global_f1 = f1_score(all_labels, all_predictions)
        global_f1_weighted = global_f1
        global_f1_macro = global_f1
        print(f"Global: Accuracy: {global_accuracy:.4f}% - F1 Score: {global_f1:.4f}")
    else:  # Multiclass
        global_f1_weighted = f1_score(all_labels, all_predictions, average='weighted')
        global_f1_macro = f1_score(all_labels, all_predictions, average='macro')
        global_f1_per_class = f1_score(all_labels, all_predictions, average=None)
        print(f"Global: Accuracy: {global_accuracy:.4f}% - F1 Score (Weighted): {global_f1_weighted:.4f} - F1 Score (Macro): {global_f1_macro:.4f}")
        print(f"F1 Score per class: {global_f1_per_class}")

    if num_regions == 1:
        # For single region, plot confusion matrix
        cm = confusion_matrix(all_labels, all_predictions)
        disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=CLASS_NAME)
        fig = plt.figure(figsize=(10, 8))
        disp.plot(ax=fig.gca(), cmap=plt.cm.Blues)
        plt.title(cmfig_title)
        plt.savefig(cmfig_filename)

################# Main Script #################

# Modify the main federated training section to use the new function
if __name__ == "__main__":
    hidden_dim = 256
    # MLP Model
    print("\n" + "="*50)
    print("Training MLP Model")
    print("="*50)
    # Initialize MLP models
    model_list=[]
    for i in range(NUM_REGION):
        model = MLPClassifier(input_features=PACKET_LEN, output_dim=NUM_CLASS)
        model.to(DEVICE)
        model_list.append(model)
    
    # Run the federated learning process with quiet=QUIET
    round_metrics, final_model = run_federated_learning(
        model_list, train_loaders, validation_loaders, test_loaders, 
        rounds=ROUNDS, quiet=QUIET, debug=DEBUG, model_name="MLP"
    )

    # Save round metrics dictionary to a file
    with open('round_metrics_FL_MLP.pkl', 'wb') as f:
        pickle.dump(round_metrics, f)

    # After all rounds, plot the convergence metrics
    plot_convergence(round_metrics, image_path='convergence_plots_FL_MLP.png')

    # Testing the final model on the all test set of all regions
    print("Testing MLP final model on test dataset")
    test_results = evaluate_model(final_model, test_loaders, quiet=QUIET)
    print_results(test_results, cmfig_title="MLP Test Confusion Matrix", cmfig_filename="confusion_matrix_MLP_test.png")

    # Evaluate the final model on the evaluation dataset
    print("Testing MLP final model on evaluation dataset")
    eval_results = evaluate_model(final_model, [eval_loader], quiet=QUIET)
    print_results(eval_results, cmfig_title="MLP Evaluation Confusion Matrix", cmfig_filename="confusion_matrix_MLP_eval.png")
    
    # Save test and evaluation results to files
    with open('test_results_FL_MLP.pkl', 'wb') as f:
        pickle.dump(test_results, f)
    with open('eval_results_FL_MLP.pkl', 'wb') as f:
        pickle.dump(eval_results, f)

    # CNN Model
    print("\n" + "="*50)
    print("Training CNN Model")
    print("="*50)
    cnn_model_list=[]
    for i in range(NUM_REGION):
        model = CNNClassifier(input_features=PACKET_LEN, output_dim=NUM_CLASS)
        model.to(DEVICE)
        cnn_model_list.append(model)
    
    round_metrics, final_cnn_model = run_federated_learning(
        cnn_model_list, train_loaders, validation_loaders, test_loaders, 
        rounds=ROUNDS, quiet=QUIET, debug=DEBUG, model_name="CNN"
    )
    
    # Save round metrics dictionary to a file
    with open('round_metrics_FL_CNN.pkl', 'wb') as f:
        pickle.dump(round_metrics, f)

    plot_convergence(round_metrics, image_path='convergence_plots_FL_CNN.png')
    
    # Testing the final CNN model on the all test set of all regions
    print("Testing CNN final model on test dataset")
    test_results = evaluate_model(final_cnn_model, test_loaders, quiet=QUIET)
    print_results(test_results, cmfig_title="CNN Test Confusion Matrix", cmfig_filename="confusion_matrix_CNN_test.png")

    print("Testing CNN final model on evaluation dataset")
    eval_results = evaluate_model(final_cnn_model, [eval_loader], quiet=QUIET)
    print_results(eval_results, cmfig_title="CNN Evaluation Confusion Matrix", cmfig_filename="confusion_matrix_CNN_eval.png")
    
    # Save test and evaluation results to files
    with open('test_results_FL_CNN.pkl', 'wb') as f:
        pickle.dump(test_results, f)
    with open('eval_results_FL_CNN.pkl', 'wb') as f:
        pickle.dump(eval_results, f)

    # RNN Model
    print("\n" + "="*50)
    print("Training RNN Model")
    print("="*50)
    rnn_model_list=[]
    for i in range(NUM_REGION):
        model = RNNClassifier(input_features=PACKET_LEN, hidden_dim=hidden_dim, output_dim=NUM_CLASS)
        model.to(DEVICE)
        rnn_model_list.append(model)
    
    round_metrics, final_rnn_model = run_federated_learning(
        rnn_model_list, train_loaders, validation_loaders, test_loaders, 
        rounds=ROUNDS, quiet=QUIET, debug=DEBUG, model_name="RNN"
    )
    
    # Save round metrics dictionary to a file
    with open('round_metrics_FL_RNN.pkl', 'wb') as f:
        pickle.dump(round_metrics, f)

    plot_convergence(round_metrics, image_path='convergence_plots_FL_RNN.png')
    
    # Testing the final RNN model on the all test set of all regions
    print("Testing RNN final model on test dataset")
    test_results = evaluate_model(final_rnn_model, test_loaders, quiet=QUIET)
    print_results(test_results, cmfig_title="RNN Test Confusion Matrix", cmfig_filename="confusion_matrix_RNN_test.png")

    print("Testing RNN final model on evaluation dataset")
    eval_results = evaluate_model(final_rnn_model, [eval_loader], quiet=QUIET)
    print_results(eval_results, cmfig_title="RNN Evaluation Confusion Matrix", cmfig_filename="confusion_matrix_RNN_eval.png")
    
    # Save test and evaluation results to files
    with open('test_results_FL_RNN.pkl', 'wb') as f:
        pickle.dump(test_results, f)
    with open('eval_results_FL_RNN.pkl', 'wb') as f:
        pickle.dump(eval_results, f)

    # LSTM Model
    print("\n" + "="*50)
    print("Training LSTM Model")
    print("="*50)
    lstm_model_list=[]
    for i in range(NUM_REGION):
        model = LSTMClassifier(input_features=PACKET_LEN, hidden_dim=hidden_dim, output_dim=NUM_CLASS)
        model.to(DEVICE)
        lstm_model_list.append(model)
    
    round_metrics, final_lstm_model = run_federated_learning(
        lstm_model_list, train_loaders, validation_loaders, test_loaders, 
        rounds=ROUNDS, quiet=QUIET, debug=DEBUG, model_name="LSTM"
    )
    
    # Save round metrics dictionary to a file
    with open('round_metrics_FL_LSTM.pkl', 'wb') as f:
        pickle.dump(round_metrics, f)

    plot_convergence(round_metrics, image_path='convergence_plots_FL_LSTM.png')
    
    # Testing the final LSTM model on the all test set of all regions
    print("Testing LSTM final model on test dataset")
    test_results = evaluate_model(final_lstm_model, test_loaders, quiet=QUIET)
    print_results(test_results, cmfig_title="LSTM Test Confusion Matrix", cmfig_filename="confusion_matrix_LSTM_test.png")

    print("Testing LSTM final model on evaluation dataset")
    eval_results = evaluate_model(final_lstm_model, [eval_loader], quiet=QUIET)
    print_results(eval_results, cmfig_title="LSTM Evaluation Confusion Matrix", cmfig_filename="confusion_matrix_LSTM_eval.png")
    
    # Save test and evaluation results to files
    with open('test_results_FL_LSTM.pkl', 'wb') as f:
        pickle.dump(test_results, f)
    with open('eval_results_FL_LSTM.pkl', 'wb') as f:
        pickle.dump(eval_results, f)

    # GRU Model
    print("\n" + "="*50)
    print("Training GRU Model")
    print("="*50)
    gru_model_list=[]
    for i in range(NUM_REGION):
        model = GRUClassifier(input_features=PACKET_LEN, hidden_dim=hidden_dim, output_dim=NUM_CLASS)
        model.to(DEVICE)
        gru_model_list.append(model)
    
    round_metrics, final_gru_model = run_federated_learning(
        gru_model_list, train_loaders, validation_loaders, test_loaders, 
        rounds=ROUNDS, quiet=QUIET, debug=DEBUG, model_name="GRU"
    )
    
    # Save round metrics dictionary to a file
    with open('round_metrics_FL_GRU.pkl', 'wb') as f:
        pickle.dump(round_metrics, f)

    plot_convergence(round_metrics, image_path='convergence_plots_FL_GRU.png')
    
    # Testing the final GRU model on the all test set of all regions
    print("Testing GRU final model on test dataset")
    test_results = evaluate_model(final_gru_model, test_loaders, quiet=QUIET)
    print_results(test_results, cmfig_title="GRU Test Confusion Matrix", cmfig_filename="confusion_matrix_GRU_test.png")

    print("Testing GRU final model on evaluation dataset")
    eval_results = evaluate_model(final_gru_model, [eval_loader], quiet=QUIET)
    print_results(eval_results, cmfig_title="GRU Evaluation Confusion Matrix", cmfig_filename="confusion_matrix_GRU_eval.png")
    
    # Save test and evaluation results to files
    with open('test_results_FL_GRU.pkl', 'wb') as f:
        pickle.dump(test_results, f)
    with open('eval_results_FL_GRU.pkl', 'wb') as f:
        pickle.dump(eval_results, f)

    # Transformer Model
    print("\n" + "="*50)
    print("Training Transformer Model")
    print("="*50)
    transformer_model_list=[]
    for i in range(NUM_REGION):
        model = TransformerClassifier(input_features=PACKET_LEN)  # Using default parameters
        model.to(DEVICE)
        transformer_model_list.append(model)
    
    round_metrics, final_transformer_model = run_federated_learning(
        transformer_model_list, train_loaders, validation_loaders, test_loaders, 
        rounds=ROUNDS, quiet=QUIET, debug=DEBUG, model_name="Transformer"
    )
    
    # Save round metrics dictionary to a file
    with open('round_metrics_FL_Transformer.pkl', 'wb') as f:
        pickle.dump(round_metrics, f)

    plot_convergence(round_metrics, image_path='convergence_plots_FL_Transformer.png')
    
    # Testing the final Transformer model on the all test set of all regions
    print("Testing Transformer final model on test dataset")
    test_results = evaluate_model(final_transformer_model, test_loaders, quiet=QUIET)
    print_results(test_results, cmfig_title="Transformer Test Confusion Matrix", cmfig_filename="confusion_matrix_Transformer_test.png")

    print("Testing Transformer final model on evaluation dataset")
    eval_results = evaluate_model(final_transformer_model, [eval_loader], quiet=QUIET)
    print_results(eval_results, cmfig_title="Transformer Evaluation Confusion Matrix", cmfig_filename="confusion_matrix_Transformer_eval.png")

    # Save test and evaluation results to files
    with open('test_results_FL_Transformer.pkl', 'wb') as f:
        pickle.dump(test_results, f)
    with open('eval_results_FL_Transformer.pkl', 'wb') as f:
        pickle.dump(eval_results, f)
        
    # torch.save(final_transformer_model.state_dict(), 'final_transformer_model.pth')

    # Two Level Transformer Model
    # print("\n" + "="*50)
    # print("Training Two Level Transformer Model")
    # print("="*50)
    # two_level_transformer_model_list=[]
    # for i in range(NUM_REGION):
    #     model = TwoLevelTransformer(input_features=PACKET_LEN, output_dim=NUM_CLASS)  # Using default parameters
    #     model.to(DEVICE)
    #     two_level_transformer_model_list.append(model)
    
    # round_metrics, final_two_level_transformer_model = run_federated_learning(
    #     two_level_transformer_model_list, train_loaders, validation_loaders, test_loaders, 
    #     rounds=ROUNDS, quiet=QUIET, debug=DEBUG, model_name="TwoLevelTransformer"
    # )

    # plot_convergence(round_metrics, image_path='convergence_plots_TwoLevelTransformer.png')

    # print("Testing Two Level Transformer final model on evaluation dataset")
    # eval_results = evaluate_model(final_two_level_transformer_model, eval_loaders, quiet=QUIET)
    # print_results(eval_results)


