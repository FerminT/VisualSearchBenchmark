from scipy.io import loadmat
import json
import os
import numpy as np

subjects_dir = 'sinfo_subj/'
subjects_files = os.listdir(subjects_dir)
save_path = '../human_scanpaths/'

receptive_size = (32, 32)
max_scanpath_length = 13

targets_found = 0
wrong_targets_found = 0
number_of_truncated_scanpaths = 0
for subject_file in subjects_files:
    subject_info = loadmat(subjects_dir + subject_file)
    subject_info = subject_info['info_per_subj']

    print('%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%')
    print('Processing ' + subject_file)
    print('\n')

    split_subject_filename = subject_file.split('_')
    subject_id = split_subject_filename[len(split_subject_filename) - 1][:-4]
    if (int(subject_id) < 10):
        subject_id = '0' + subject_id

    json_subject = dict()
    for record in range(len(subject_info[0])):
        image_name   = subject_info['image_name'][0][record][0]
        image_height = int(subject_info['image_size'][0][record][0][0])
        image_width  = int(subject_info['image_size'][0][record][0][1])

        screen_height = int(subject_info['screen_size'][0][record][0][0])
        screen_width  = int(subject_info['screen_size'][0][record][0][1])

        target_bbox = subject_info['target_rect'][0][record][0]
        # Swap values, new order is [lower_row, lower_column, upper_row, upper_column]
        target_bbox[0], target_bbox[1], target_bbox[2], target_bbox[3] = target_bbox[1] - 1, target_bbox[0] - 1, target_bbox[3] - 1, target_bbox[2] - 1
        target_found = bool(subject_info['target_found'][0][record][0][0])

        trial_max_fixations = int(subject_info['nsaccades_allowed'][0][record][0][0]) + 1

        # Subtract one, since Python indexes images from zero
        fix_posX = subject_info['x'][0][record][0].astype(float) - 1
        fix_posY = subject_info['y'][0][record][0].astype(float) - 1
        fix_time = subject_info['dur'][0][record][0]

        # Truncate negative values
        fix_posX = np.where(fix_posX < 0, 0, fix_posX)
        fix_posY = np.where(fix_posY < 0, 0, fix_posY)

        if (len(fix_posX) == 0):
            print("Subject: " + subject_id + "; stimuli: " + image_name + "; trial: " + str(record + 1) + ". Empty scanpath")
            continue

        scanpath_length = len(fix_posX)
        if trial_max_fixations > max_scanpath_length:
            trial_max_fixations = max_scanpath_length
            if scanpath_length > max_scanpath_length:
                # Truncate scanpath
                fix_posX = fix_posX[:max_scanpath_length]
                fix_posY = fix_posY[:max_scanpath_length]
                scanpath_length = max_scanpath_length
                if target_found:
                    target_found = False
            number_of_truncated_scanpaths += 1
                    

        last_fixation_X = fix_posX[scanpath_length - 1]
        last_fixation_Y = fix_posY[scanpath_length - 1]
        between_bounds = (target_bbox[0] - receptive_size[0] <= last_fixation_Y) and (target_bbox[2] + receptive_size[0] >= last_fixation_Y) and (target_bbox[1] - receptive_size[1] <= last_fixation_X) and (target_bbox[3] + receptive_size[1] >= last_fixation_X)
        if target_found:
            if between_bounds:
                targets_found += 1
            else:
                print("Subject: " + subject_id + "; stimuli: " + image_name + "; trial: " + str(record + 1) + ". Last fixation doesn't match target's bounds")
                print("Target's bounds: " + str(target_bbox) + ". Last fixation: " + str((last_fixation_Y, last_fixation_X)) + '\n')
                wrong_targets_found += 1
                target_found = False

        json_subject[image_name] = {"subject" : subject_id, "dataset" : "cIBS Dataset", "image_height" : image_height, "image_width" : image_width, "screen_height" : screen_height, "screen_width" : screen_width, "receptive_height" : receptive_size[0], "receptive_width" : receptive_size[1], \
            "target_found" : target_found, "target_bbox" : target_bbox.tolist(), "X" : fix_posX.tolist(), "Y" : fix_posY.tolist(), "T" : fix_time.tolist(), "target_object" : "TBD", "max_fixations" : trial_max_fixations}
    
    if not(os.path.exists(save_path)):
        os.mkdir(save_path)
    subject_json_filename = 'subj' + subject_id + '_scanpaths.json'
    with open(save_path + subject_json_filename, 'w') as fp:
        json.dump(json_subject, fp, indent = 4)
        fp.close()

print("Targets found: " + str(targets_found) + ". Wrong targets found: " + str(wrong_targets_found))
print("Truncated scanpaths: " + str(number_of_truncated_scanpaths))
