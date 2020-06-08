import torch
import numpy as np
from torch.utils.data import Dataset
from utils.map_utils import Map, depth_to_xy, Visualizer
from utils.utils import fig2data
import glob, os.path as osp
import random
import math
import matplotlib.pyplot as plt

class cvae_dataset(Dataset):
    def __init__(self, cfg):

        # store useful things ...
        self.cfg = cfg
        self.crop_size = cfg.data.crop_size
        self.downsample_factor = cfg.data.downsample_factor
        self.laser_max_range = cfg.data.laser_max_range
        self.n_ray = cfg.data.n_ray
        self.fov = np.deg2rad(cfg.data.fov)

        self.occu_map_paths= sorted(glob.glob(osp.join(cfg.data.occu_map_dir,'*')))
        self.length = len(self.occu_map_paths)


    def __len__(self):
        return self.length

    def __getitem__(self, index):

        occu_map_path = self.occu_map_paths[index]

        ## load map and random crop
        if self.crop_size == 0:
            m = Map(osp.join(occu_map_path, 'floorplan.yaml'), 
                    laser_max_range=self.laser_max_range, 
                    downsample_factor=self.downsample_factor)
        else:
            m = Map(osp.join(occu_map_path, 'floorplan.yaml'), 
                    laser_max_range=self.laser_max_range, 
                    downsample_factor=self.downsample_factor,
                    crop_size=self.crop_size)

        occupancy = m.get_occupancy_grid()
        W_world = occupancy.shape[1]*m.resolution
        H_world = occupancy.shape[0]*m.resolution

        ## uniformly random sample state in freespace
        while True:
            world_pos_x = np.random.uniform(0, W_world, 1)[0]
            world_pos_y = np.random.uniform(0, H_world, 1)[0]
            grid_pos_x, grid_pos_y = m.grid_coord(world_pos_x, world_pos_y)
            grid_pos_x = np.clip(grid_pos_x, 0, occupancy.shape[1]-1)
            grid_pos_y = np.clip(grid_pos_y, 0, occupancy.shape[0]-1)

            if occupancy[grid_pos_y, grid_pos_x]== 0:
                break
        
        world_pos = np.array([world_pos_x, world_pos_y])
        ## uniformly random sample heading
        heading = np.random.uniform(0, 360, 1)[0]
        heading = np.deg2rad(heading)
        depth = m.get_1d_depth(world_pos, heading, self.fov, self.n_ray)
        depth_xy = depth_to_xy(depth, world_pos, heading, self.fov)

        ## clip depth
        np.clip(depth_xy[:, 0], 0, W_world, out=depth_xy[:, 0])
        np.clip(depth_xy[:, 1], 0, H_world, out=depth_xy[:, 1])

        ## normalize state position and depth info to [0,1]
        world_pos_x = world_pos_x/W_world
        world_pos_y = world_pos_y/H_world
        depth_xy[:,0] = depth_xy[:,0]/W_world
        depth_xy[:,1] = depth_xy[:,1]/H_world
        heading = heading/(2*math.pi)

    
        state = torch.Tensor(np.array([world_pos_x, world_pos_y, heading]))
        occupancy = torch.Tensor(occupancy).unsqueeze(0) ## change shape to (1, W, H)
        depth_xy = torch.Tensor(depth_xy).view(-1)

        return occupancy, depth_xy, state, occu_map_path, W_world, H_world

    
class cnn_dataset(Dataset):
    def __init__(self, cfg):
        self.cfg = cfg
        
        self.a = cfg.model
        
        self.crop_size = cfg.data.crop_size
        self.downsample_factor = cfg.data.downsample_factor
        self.laser_max_range = cfg.data.laser_max_range
        self.n_ray = cfg.data.n_ray
        self.fov = cfg.data.fov

        self.num_bin = cfg.data.num_bin

        self.occu_map_paths= sorted(glob.glob(osp.join(cfg.data.occu_map_dir,'*')))
        self.length = len(self.occu_map_paths)

    def __len__(self):
        return self.length

    def __getitem__(self, index):
        occu_map_path = self.occu_map_paths[index]

        ## load map and random crop
        if self.crop_size == 0:
            m = Map(osp.join(occu_map_path, 'floorplan.yaml'),
                    laser_max_range=self.laser_max_range,
                    downsample_factor=self.downsample_factor)
        else:
            m = Map(osp.join(occu_map_path, 'floorplan.yaml'),
                    laser_max_range=self.laser_max_range,
                    downsample_factor=self.downsample_factor,
                    crop_size=self.crop_size)

        occupancy = m.get_occupancy_grid()
        W_world = occupancy.shape[1] * m.resolution
        H_world = occupancy.shape[0] * m.resolution

        ## uniformly random sample state in freespace
        while True:
            world_pos_x = np.random.uniform(0, W_world, 1)[0]
            world_pos_y = np.random.uniform(0, H_world, 1)[0]
            grid_pos_x, grid_pos_y = m.grid_coord(world_pos_x, world_pos_y)
            grid_pos_x = np.clip(grid_pos_x, 0, occupancy.shape[1] - 1)
            grid_pos_y = np.clip(grid_pos_y, 0, occupancy.shape[0] - 1)

            if occupancy[grid_pos_y, grid_pos_x] == 0:
                break

        world_pos = np.array([world_pos_x, world_pos_y])
        ## uniformly random sample heading
        heading = np.random.uniform(0, 360, 1)[0]
        heading = np.deg2rad(heading)
        depth = m.get_1d_depth(world_pos, heading, self.fov, self.n_ray)
        depth_xy = depth_to_xy(depth, world_pos, heading, self.fov)

        ## clip depth
        np.clip(depth_xy[:, 0], 0, W_world, out=depth_xy[:, 0])
        np.clip(depth_xy[:, 1], 0, H_world, out=depth_xy[:, 1])

        ## normalize state position and depth info to [0,1]
        world_pos_x_cls = (world_pos_x) // (W_world / self.num_bin)
        world_pos_y_cls = (world_pos_y) // (H_world / self.num_bin)
        depth_xy[:, 0] = depth_xy[:, 0] / W_world
        depth_xy[:, 1] = depth_xy[:, 1] / H_world
        heading = heading / (2 * math.pi)
        heading_cls = (heading) // (1 / self.num_bin)
        cls = np.array([world_pos_x_cls, world_pos_y_cls, heading_cls])

        cls = torch.LongTensor(cls)
        occupancy = torch.Tensor(occupancy).unsqueeze(0) ## change shape to (1, W, H)
        depth_xy = torch.Tensor(depth_xy).view(-1)

        return occupancy, depth_xy, cls, occu_map_path, W_world, H_world
