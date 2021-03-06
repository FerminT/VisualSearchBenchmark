import json
import numpy as np
from multimatch import Multimatch
from cumulative_performance import Cumulative_performance
from os import listdir, path

results_dir  = '../Results/'
datasets_dir = '../Datasets/'

dataset_results_dirs = listdir(results_dir)
for dataset in dataset_results_dirs:
    dataset_name = dataset.split('_')[0]
    dataset_path = path.join(datasets_dir, dataset_name)
    human_scanpaths_dir = dataset_path + '/human_scanpaths/'
    dataset_results_dir = results_dir + dataset + '/'
    with open(path.join(dataset_path, 'dataset_info.json')) as fp:
        dataset_info = json.load(fp)

    max_scanpath_length = dataset_info['max_scanpath_length']
    number_of_images    = dataset_info['number_of_images']

    # Initialize objects
    multimatch = Multimatch(dataset_name, human_scanpaths_dir, dataset_results_dir)

    subjects_cumulative_performance = Cumulative_performance(dataset_name, number_of_images, max_scanpath_length)
    subjects_cumulative_performance.add_human_mean(human_scanpaths_dir)

    # Compute models metrics and compare them with human subjects metrics
    models = listdir(dataset_results_dir)
    for model_name in models:
        if not(path.isdir(path.join(dataset_results_dir, model_name))):
            continue

        model_scanpaths_file = dataset_results_dir + model_name + '/Scanpaths.json'
        with open(model_scanpaths_file, 'r') as fp:
            model_scanpaths = json.load(fp)
        
        subjects_cumulative_performance.add_model(model_name, model_scanpaths)

        # Human multimatch scores are different for each model, since each model uses different image sizes
        multimatch.load_human_mean_per_image(model_name, model_scanpaths)
        multimatch.add_model_vs_humans_mean_per_image(model_name, model_scanpaths)
    
    subjects_cumulative_performance.plot(save_path=dataset_results_dir)
    multimatch.plot(save_path=dataset_results_dir)