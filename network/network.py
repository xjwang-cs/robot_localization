import torch
import torch.nn as nn

activation = {
    "tanh": nn.Tanh,
    "sigm": nn.Sigmoid,
    "relu": nn.ReLU,
}

class basic_MLP(nn.Module):
    def __init__(self, cfg, input_dim):
        super(basic_MLP, self).__init__()
        self.input_dim = input_dim
        self.hidden_dim = cfg.model.hidden_dim        
        self.activation_func = activation[cfg.model.activation_func]
        self.activation = self.activation_func()

        self.backbone = nn.Sequential(
            nn.Linear(self.input_dim, self.hidden_dim),
            self.activation_func(),
            nn.Linear(self.hidden_dim, self.hidden_dim),
            self.activation_func(),
        )

    def forward(self, x):
        return self.backbone(x)

class basic_CNN(nn.Module):
    def __init__(self, cfg):
        super(basic_CNN, self).__init__()
        self.input_dim = cfg.data.input_occumap_dim   
        self.hidden_dim = cfg.model.hidden_dim   
        self.activation_func = activation[cfg.model.activation_func]
        self.activation = self.activation_func()
        self.backbone = nn.Sequential(
            nn.Conv2d(self.input_dim[0], self.hidden_dim, 7, 2),
            self.activation_func(),
            nn.MaxPool2d(3, 2),
            nn.Conv2d(self.hidden_dim, self.hidden_dim, 3, 1),
            self.activation_func(),
            nn.MaxPool2d(3, 2),
            nn.Conv2d(self.hidden_dim, self.hidden_dim, 3, 1),
            self.activation_func(),
            nn.AdaptiveAvgPool2d((1, 1)),
        )

    def forward(self, x):
        return self.backbone(x)

class Encoder(nn.Module):

    def __init__(self, cfg):
        super(Encoder, self).__init__()
        self.input_fc_dim = cfg.data.input_depth_dim + cfg.data.input_state_dim
        self.latent_z_dim = cfg.model.latent_z_dim
        self.hidden_dim = cfg.model.hidden_dim

        self.fc = basic_MLP(cfg, self.input_fc_dim) ## for encoding depth and state input
        self.cnn = basic_CNN(cfg) ## for encoding occu map

        ## concatenate the output from cnn model and fc model, thus the input is hidden_dim + hidden_dim
        self.linear_means = nn.Linear(2*self.hidden_dim, self.latent_z_dim)
        self.linear_log_var = nn.Linear(2*self.hidden_dim, self.latent_z_dim)
    def forward(self, state, occupancy, depth):
 
        x1 = self.fc(torch.cat((state, depth), 1))
        x2 = self.cnn(occupancy)

        batch_size = x2.shape[0]
        x2 = x2.view(batch_size,-1) ## flatten the output from cnn

        x = torch.cat((x1, x2), 1)
        means = self.linear_means(x)
        log_vars = self.linear_log_var(x)

        return means, log_vars

class Decoder(nn.Module):

    def __init__(self, cfg):

        super(Decoder, self).__init__()
        
        self.input_state_dim = cfg.data.input_state_dim
        self.latent_z_dim = cfg.model.latent_z_dim
        self.input_fc_dim = cfg.data.input_depth_dim + self.latent_z_dim
        self.hidden_dim = cfg.model.hidden_dim

        self.fc = basic_MLP(cfg, self.input_fc_dim) ## for decoding depth and latent variable
        self.cnn = basic_CNN(cfg) ## for encoding occu map

        self.linear_out = nn.Linear(2*self.hidden_dim, self.input_state_dim)
        self.sigmoid_out = nn.Sigmoid()
        
    def forward(self, z, occupancy, depth):
        x1 = self.fc(torch.cat((z, depth), 1))
        x2 = self.cnn(occupancy)
        batch_size = x2.shape[0]
        x2 = x2.view(batch_size,-1) ## flatten the output from cnn
        x = self.linear_out(torch.cat((x1, x2), 1))
        x = self.sigmoid_out(x) ## the output should be mapped to (0,1)
        return x


class SeqEncoder(nn.Module):

    def __init__(self, cfg):
        super(SeqEncoder, self).__init__()
        self.input_fc_dim = cfg.data.input_depth_dim + cfg.data.input_state_dim
        self.latent_z_dim = cfg.model.latent_z_dim
        self.hidden_dim = cfg.model.hidden_dim

        self.fc = basic_MLP(cfg, self.input_fc_dim)  ## for encoding depth and state input
        self.cnn = basic_CNN(cfg)  ## for encoding occu map
        self.lstm = nn.LSTM(2 * self.hidden_dim, self.hidden_dim, 1, batch_first=True)

        ## concatenate the output from cnn model and fc model, thus the input is hidden_dim + hidden_dim
        self.linear_means = nn.Linear(self.hidden_dim, self.latent_z_dim)
        self.linear_log_var = nn.Linear(self.hidden_dim, self.latent_z_dim)

    def forward(self, state, occupancy, depth):
        x1 = self.fc(torch.cat((state, depth), 2))
        x2 = self.cnn(occupancy)

        batch_size = x2.shape[0]
        x2 = x2.view(batch_size, 1, -1).repeat((1, x1.shape[1], 1))  ## flatten the output from cnn

        x = torch.cat((x1, x2), 2)
        x, _ = self.lstm(x)
        means = self.linear_means(x)
        log_vars = self.linear_log_var(x)

        return means, log_vars


class SeqDecoder(nn.Module):

    def __init__(self, cfg):
        super(SeqDecoder, self).__init__()

        self.input_state_dim = cfg.data.input_state_dim
        self.latent_z_dim = cfg.model.latent_z_dim
        self.input_fc_dim = cfg.data.input_depth_dim + self.latent_z_dim
        self.hidden_dim = cfg.model.hidden_dim

        self.fc = basic_MLP(cfg, self.input_fc_dim)  ## for decoding depth and latent variable
        self.cnn = basic_CNN(cfg)  ## for encoding occu map
        self.lstm = nn.LSTM(2 * self.hidden_dim, self.hidden_dim, 1, batch_first=True)

        self.linear_out = nn.Linear(self.hidden_dim, self.input_state_dim)
        self.sigmoid_out = nn.Sigmoid()

    def forward(self, z, occupancy, depth):
        x1 = self.fc(torch.cat((z, depth), 2))
        x2 = self.cnn(occupancy)
        batch_size = x2.shape[0]
        x2 = x2.view(batch_size, 1, -1).repeat((1, x1.shape[1], 1))  ## flatten the output from cnn
        x = torch.cat((x1, x2), 2)
        x, _ = self.lstm(x)
        x = self.linear_out(x)
        x = self.sigmoid_out(x)  ## the output should be mapped to (0,1)
        return x


class ClassificationDecoder(nn.Module):

    def __init__(self, cfg):
        super(ClassificationDecoder, self).__init__()

        self.input_state_dim = cfg.data.input_state_dim
        self.input_fc_dim = cfg.data.input_depth_dim
        self.hidden_dim = cfg.model.hidden_dim

        self.fc = basic_MLP(cfg, self.input_fc_dim)  ## for decoding depth and latent variable
        self.cnn = basic_CNN(cfg)  ## for encoding occu map

        self.linear_out_w = nn.Linear(2 * self.hidden_dim, cfg.data.num_bin)
        self.linear_out_h = nn.Linear(2 * self.hidden_dim, cfg.data.num_bin)
        self.linear_out_r = nn.Linear(2 * self.hidden_dim, cfg.data.num_bin)

    def forward(self, occupancy, depth):
        x1 = self.fc(depth)
        x2 = self.cnn(occupancy)
        batch_size = x2.shape[0]
        x2 = x2.view(batch_size, -1)  ## flatten the output from cnn
        rep = torch.cat((x1, x2), 1)
        w = self.linear_out_w(rep).unsqueeze(1)
        h = self.linear_out_h(rep).unsqueeze(1)
        r = self.linear_out_r(rep).unsqueeze(1)
        return torch.cat((w, h, r), 1)


class RegressionDecoder(nn.Module):

    def __init__(self, cfg):
        super(RegressionDecoder, self).__init__()

        self.input_state_dim = cfg.data.input_state_dim
        self.input_fc_dim = cfg.data.input_depth_dim
        self.hidden_dim = cfg.model.hidden_dim

        self.fc = basic_MLP(cfg, self.input_fc_dim)  ## for decoding depth and latent variable
        self.cnn = basic_CNN(cfg)  ## for encoding occu map

        self.linear_out = nn.Linear(2*self.hidden_dim, self.input_state_dim)
        self.sigmoid_out = nn.Sigmoid()

    def forward(self, occupancy, depth):
        x1 = self.fc(depth)
        x2 = self.cnn(occupancy)
        batch_size = x2.shape[0]
        x2 = x2.view(batch_size, -1)  ## flatten the output from cnn
        x = self.linear_out(torch.cat((x1, x2), 1))
        x = self.sigmoid_out(x) ## the output should be mapped to (0,1)
        return x


class CVAE(nn.Module):

    def __init__(self, cfg):
        super(CVAE, self).__init__()
        self.latent_z_dim = cfg.model.latent_z_dim
        self.encoder = Encoder(cfg)
        self.decoder = Decoder(cfg)

    def forward(self, state, occupancy, depth):

        batch_size = state.size(0)
        assert(occupancy.size(0) == batch_size)
        assert(depth.size(0) == batch_size)

        means, log_var = self.encoder(state, occupancy, depth)

        std = torch.exp(0.5 * log_var)
        eps = torch.randn([batch_size, self.latent_z_dim]).to(std.device)
        z = eps * std + means

        recon_state = self.decoder(z, occupancy, depth)

        return recon_state, means, log_var, z

    def inference(self, occupancy, depth):

        batch_size = occupancy.size(0)
        z = torch.randn([batch_size, self.latent_z_dim]).to(occupancy.device)

        recon_state = self.decoder(z, occupancy, depth)

        return recon_state

class SeqCVAE(nn.Module):

    def __init__(self, cfg):
        super(SeqCVAE, self).__init__()
        self.latent_z_dim = cfg.model.latent_z_dim
        self.encoder = SeqEncoder(cfg)
        self.decoder = SeqDecoder(cfg)

    def forward(self, state, occupancy, depth):

        batch_size = state.size(0)
        seq_horizon = state.size(1)
        assert(occupancy.size(0) == batch_size)
        assert(depth.size(0) == batch_size)

        means, log_var = self.encoder(state, occupancy, depth)

        std = torch.exp(0.5 * log_var)
        eps = torch.randn([batch_size, seq_horizon, self.latent_z_dim]).to(std.device)
        z = eps * std + means

        recon_state = self.decoder(z, occupancy, depth)

        return recon_state, means, log_var, z

    def inference(self, occupancy, depth):

        batch_size = occupancy.size(0)
        seq_horizon = depth.size(1)
        z = torch.randn([batch_size, seq_horizon, self.latent_z_dim]).to(occupancy.device)

        recon_state = self.decoder(z, occupancy, depth)

        return recon_state

class Classfication_model(nn.Module):

    def __init__(self, cfg):
        super(Classfication_model, self).__init__()
        self.decoder = ClassificationDecoder(cfg)

    def forward(self, occupancy, depth):
        out = self.decoder(occupancy, depth)
        return out

class Regression_model(nn.Module):

    def __init__(self, cfg):
        super(Regression_model, self).__init__()
        self.decoder = RegressionDecoder(cfg)

    def forward(self, occupancy, depth):
        out = self.decoder(occupancy, depth)
        return out

## to be implemented for state classification
class CNN(nn.Module):
    def __init__(self, cfg):
        super(CNN, self).__init__()
        self.input_dim = 100*4
        self.conv1 = nn.Sequential(
            nn.Conv2d(1, 16, 5, 1, 2),
            nn.ReLU(),
            nn.AvgPool2d(2, 2)       #50*2
        )

        self.conv2 = nn.Sequential(
            nn.Conv2d(16, 32, 5, 1, 2),
            nn.ReLU(),
            nn.AvgPool2d(2, 2)        #25*1
        )

        self.fc1 = nn.Sequential(
            nn.Linear(32*25*1, 256),
            nn.BatchNorm1d(256),
            nn.ReLU()
        )

        self.fc2 = nn.Sequential(
            nn.Linear(256, 128),
            nn.BatchNorm1d(128),
            nn.ReLU()
        )
        self.fc3 = nn.Linear(128, 64)
        
        
    def forward(self, x):
        x = self.conv1(x)
        x = self.conv2(x)
        x = x.view(x.size()[0], -1)
        x = self.fc1(x)
        x = self.fc2(x)
        x = self.fc3(x)
        return x
