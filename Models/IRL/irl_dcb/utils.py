import numpy as np
import torch
import json
import warnings
import os
from math import floor
from torch.distributions import Categorical
warnings.filterwarnings("ignore", category=UserWarning)

def rescale_coordinate(value, old_size, new_size):
    return floor((value / old_size) * new_size)

def add_scanpath_to_dict(model_name, image_name, image_size, scanpath_x, scanpath_y, target_object, cell_size, max_saccades, dataset_name, dict_):
    dict_[image_name] = {'subject' : model_name, 'dataset' : dataset_name, 'image_height' : image_size[0], 'image_width' : image_size[1], \
        'receptive_height' : cell_size, 'receptive_width' : cell_size, 'target_found' : False, 'target_bbox' : np.zeros(shape=4), \
                 'X' : list(map(int, scanpath_x)), 'Y' : list(map(int, scanpath_y)), 'target_object' : target_object, 'max_fixations' : max_saccades + 1
        }

def save_scanpaths(output_path, scanpaths):
    if not os.path.exists(output_path):
        os.makedirs(output_path)
    save_to_json(output_path + 'Scanpaths.json', scanpaths)

def save_to_json(file, data):
    with open(file, 'w') as json_file:
        json.dump(data, json_file, indent=4)

def cutFixOnTarget(trajs, target_annos):
    for image_name in trajs:
        traj = trajs[image_name]
        key = traj['target_object'] + '_' + image_name
        bbox = target_annos[key]
        traj_len = get_num_step2target(traj['X'], traj['Y'], bbox)
        if traj_len != 1000:
            traj['target_found'] = True
        traj['X'] = traj['X'][:traj_len]
        traj['Y'] = traj['Y'][:traj_len]
        traj['target_bbox'] = [bbox[1], bbox[0], bbox[1] + bbox[3], bbox[0] + bbox[2]]

def pos_to_action(center_x, center_y, patch_size, patch_num):
    x = center_x // patch_size[0]
    y = center_y // patch_size[1]

    return int(patch_num[0] * y + x)

def action_to_pos(acts, patch_size, patch_num):
    patch_y = acts // patch_num[0]
    patch_x = acts % patch_num[0]

    pixel_x = patch_x * patch_size[0] + patch_size[0] / 2
    pixel_y = patch_y * patch_size[1] + patch_size[1] / 2
    return pixel_x, pixel_y

def select_action(obs, policy, sample_action, action_mask=None,
                  softmask=False, eps=1e-12):
    probs, values = policy(*obs)
    if sample_action:
        m = Categorical(probs)
        if action_mask is not None:
            # prevent sample previous actions by re-normalizing probs
            probs_new = probs.clone().detach()
            if softmask:
                probs_new = probs_new * action_mask
            else:
                probs_new[action_mask] = eps
            
            probs_new /= probs_new.sum(dim=1).view(probs_new.size(0), 1)
                
            m_new = Categorical(probs_new)
            actions = m_new.sample()
        else:
            actions = m.sample()
        log_probs = m.log_prob(actions)
        return actions.view(-1), log_probs, values.view(-1), probs
    else:
        probs_new = probs.clone().detach()
        probs_new[action_mask.view(probs_new.size(0), -1)] = 0
        actions = torch.argmax(probs_new, dim=1)
        return actions.view(-1), None, None, None

def collect_trajs(env,
                  policy,
                  patch_num,
                  max_traj_length,
                  is_eval=True,
                  sample_action=True):

    rewards = []
    obs_fov = env.observe()
    act, log_prob, value, prob = select_action((obs_fov, env.task_ids),
                                               policy,
                                               sample_action,
                                               action_mask=env.action_mask)
    status = [env.status]
    values = [value]
    log_probs = [log_prob]
    SASPs = []

    i = 0
    if is_eval:
        actions = []
        while i < max_traj_length:
            new_obs_fov, curr_status = env.step(act)
            status.append(curr_status)
            actions.append(act)
            obs_fov = new_obs_fov
            act, log_prob, value, prob_new = select_action(
                (obs_fov, env.task_ids),
                policy,
                sample_action,
                action_mask=env.action_mask)
            i = i + 1

        trajs = {
            'status': torch.stack(status),
            'actions': torch.stack(actions)
        }

    return trajs

def get_num_step2target(X, Y, bbox):
    X, Y = np.array(X), np.array(Y)
    on_target_X = np.logical_and(X > bbox[0], X < bbox[0] + bbox[2])
    on_target_Y = np.logical_and(Y > bbox[1], Y < bbox[1] + bbox[3])
    on_target = np.logical_and(on_target_X, on_target_Y)
    if np.sum(on_target) > 0:
        first_on_target_idx = np.argmax(on_target)
        return first_on_target_idx + 1
    else:
        return 1000  # some big enough number

def get_num_steps(trajs, target_annos, task_names):
    num_steps = {}
    for task in task_names:
        task_trajs = list(filter(lambda x: x['task'] == task, trajs))
        num_steps_task = np.ones(len(task_trajs), dtype=np.uint8)
        for i, traj in enumerate(task_trajs):
            key = traj['task'] + '_' + traj['name']
            bbox = target_annos[key]
            step_num = get_num_step2target(traj['X'], traj['Y'], bbox)
            num_steps_task[i] = step_num
            traj['X'] = traj['X'][:step_num]
            traj['Y'] = traj['Y'][:step_num]
        num_steps[task] = num_steps_task
    return num_steps

def calc_overlap_ratio(bbox, patch_size, patch_num):
    """
    compute the overlaping ratio of the bbox and each patch (10x16)
    """
    patch_area = float(patch_size[0] * patch_size[1])
    aoi_ratio = np.zeros((1, patch_num[1], patch_num[0]), dtype=np.float32)

    tl_x, tl_y = bbox[0], bbox[1]
    br_x, br_y = bbox[0] + bbox[2], bbox[1] + bbox[3]
    lx, ux = tl_x // patch_size[0], br_x // patch_size[0]
    ly, uy = tl_y // patch_size[1], br_y // patch_size[1]

    for x in range(lx, ux + 1):
        for y in range(ly, uy + 1):
            patch_tlx, patch_tly = x * patch_size[0], y * patch_size[1]
            patch_brx, patch_bry = patch_tlx + patch_size[
                0], patch_tly + patch_size[1]

            aoi_tlx = tl_x if patch_tlx < tl_x else patch_tlx
            aoi_tly = tl_y if patch_tly < tl_y else patch_tly
            aoi_brx = br_x if patch_brx > br_x else patch_brx
            aoi_bry = br_y if patch_bry > br_y else patch_bry

            aoi_ratio[0, y, x] = max((aoi_brx - aoi_tlx), 0) * max(
                (aoi_bry - aoi_tly), 0) / float(patch_area)

    return aoi_ratio

def foveal2mask(x, y, r, h, w):
    Y, X = np.ogrid[:h, :w]
    dist = np.sqrt((X - x)**2 + (Y - y)**2)
    mask = dist <= r
    return mask.astype(np.float32)

def multi_hot_coding(bbox, patch_size, patch_num):
    """
    compute the overlaping ratio of the bbox and each patch (10x16)
    """
    thresh = 0
    aoi_ratio = calc_overlap_ratio(bbox, patch_size, patch_num)
    hot_ind = aoi_ratio > thresh
    while hot_ind.sum() == 0:
        thresh *= 0.8
        hot_ind = aoi_ratio > thresh

    aoi_ratio[hot_ind] = 1
    aoi_ratio[np.logical_not(hot_ind)] = 0

    return aoi_ratio[0]

def actions2scanpaths(actions, patch_num, im_w, im_h, dataset_name, patch_size, max_saccades):
    scanpaths = {}
    for traj in actions:
        task_name, img_name, initial_fix, condition, actions = traj
        actions = actions.to(dtype=torch.float32)
        py = (actions // patch_num[0]) / float(patch_num[1])
        px = (actions % patch_num[0]) / float(patch_num[0])
        fixs = torch.stack([px, py])
        fixs = np.concatenate([np.array([[float(initial_fix[0])], [float(initial_fix[1])]]),
                               fixs.cpu().numpy()],
                              axis=1)
        add_scanpath_to_dict('IRL Model', img_name, (im_h, im_w), fixs[0] * im_w, fixs[1] * im_h, task_name, patch_size, max_saccades, dataset_name, scanpaths)
    return scanpaths
                                      
def _file_best(name):
    return "trained_{}.pkg".format(name)

def load(step_or_path, model, name, optim=None, pkg_dir="", device=None):
    step = step_or_path
    save_path = None
    if isinstance(step, int):
        save_path = os.path.join(pkg_dir, _file_at_step(step, name))
    if isinstance(step, str):
        if pkg_dir is not None:
            if step == "best":
                save_path = os.path.join(pkg_dir, _file_best(name))
            else:
                save_path = os.path.join(pkg_dir, step)
        else:
            save_path = step
    if save_path is not None and not os.path.exists(save_path):
        print("[Checkpoint]: Failed to find {}".format(save_path))
        return
    if save_path is None:
        print("[Checkpoint]: Cannot load the checkpoint")
        return

    # begin to load
    state = torch.load(save_path, map_location=device)
    global_step = state["global_step"]
    model.load_state_dict(state["model"])
    if optim is not None:
        optim.load_state_dict(state["optim"])

    print("Loaded {} successfully".format(save_path))
    return global_step
