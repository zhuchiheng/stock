from data import trade
from StockAI.models import policy
from util import logger
from keras.callbacks import ModelCheckpoint, Callback
import os
import json
import pandas as pd
import numpy as np


class MetadataWriterCallback(Callback):
    def __init__(self, path):
        self.file = path
        self.metadata = {'epochs': [], 'best_epoch': 0}

    def on_epoch_end(self, epoch, logs={}):
        # in case appending to logs (resuming training), get epoch number ourselves
        epoch = len(self.metadata['epochs'])

        self.metadata['epochs'].append(logs)

        if 'val_loss' in logs:
            key = 'val_loss'
        else:
            key = 'loss'

        best_loss = self.metadata['epochs'][self.metadata['best_epoch']][key]
        if logs.get(key) < best_loss:
            self.metadata['best_epoch'] = epoch

        with open(self.file, 'w') as f:
            json.dump(self.metadata, f)


def train(timesteps=15,
          data_dim=15,
          datatype='lstm',
          debug=False,
          nb_epoch=50,
          predict_days=18,
          batch_size=32):
    USER_HOME = os.environ['HOME']
    log = logger.log
    network = policy.LSTMPolicy.create_network(data_dim=data_dim,
                                              timesteps=timesteps)

    df, codes = trade.get_hist_orgindata(debug)
    split = 0.3
    n_codes = len(codes)
    n_valid_codes = int(np.round(split * n_codes))
    valid_codes = codes[0:n_valid_codes]
    train_codes = codes[n_valid_codes:n_codes]
    df_train = df[[xcode in train_codes for xcode in df.code]]
    df_valid = df[[xcode in valid_codes for xcode in df.code]]
    del df
    train_generator = trade.get_hist_generator(seg_len=timesteps,
                                               datatype=datatype,
                                               debug=debug,
                                               predict_days=predict_days,
                                               batch_size=batch_size,
                                               df=df_train)
    valid_generator = trade.get_hist_generator(seg_len=timesteps,
                                               datatype=datatype,
                                               debug=debug,
                                               predict_days=predict_days,
                                               batch_size=batch_size,
                                               df=df_valid)
    n_train_batch = trade.get_hist_n_batch(
        seg_len=timesteps,
        datatype=datatype,
        debug=debug,
        predict_days=predict_days,
        batch_size=batch_size,
        df=df_train)
    n_valid_batch = trade.get_hist_n_batch(
        seg_len=timesteps,
        datatype=datatype,
        debug=debug,
        predict_days=predict_days,
        batch_size=batch_size,
        df=df_valid)

    out_directory_path = USER_HOME + '/dw/'

    if not os.path.exists(out_directory_path):
        os.makedirs(out_directory_path)
    meta_file = os.path.join(out_directory_path, 'metadata.json')
    meta_writer = MetadataWriterCallback(meta_file)

    checkpoint_template = os.path.join(out_directory_path,
                                       'weights.{epoch:05d}.h5')
    checkpointer = ModelCheckpoint(checkpoint_template)

    weights_path = get_best_weights(meta_file)
    if weights_path:
        network.load_weights(weights_path)

    network.fit_generator(train_generator,
                          samples_per_epoch=n_train_batch * batch_size,
                          nb_epoch=nb_epoch,
                          callbacks=[checkpointer, meta_writer],
                          validation_data=valid_generator,
                          nb_val_samples=n_valid_batch * batch_size)


def get_best_weights(meta_file):
    best_weight_file = None
    if os.path.exists(meta_file):
        with open(meta_file, 'r') as f:
            metadata = json.load(f)
            best_weight_file = 'weights.%05d.h5' % metadata['best_epoch']
    if best_weight_file:
        weights_path = os.path.join(
            os.path.dirname(meta_file), best_weight_file)
        return weights_path
