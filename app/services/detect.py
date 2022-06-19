import os
import numpy as np
import tensorflow as tf
import matplotlib.pyplot as plt
from sklearn.model_selection import train_test_split
from db import helpers as db
from models.cnn_lstm_ae import CnnLstmAe


class Detect():
  def __init__(self, conn):
    self.conn = conn

  def __call__(self):
    rounds = self.__get_rounds()
    port_usage = self.__get_port_usage(rounds)

    ports_per_round = self.port_usage_per_round(port_usage, rounds)

    # Create model
    pbounds_default = {
      'conv_filters': 32,
      'conv_kernel_size': 128,
      'activation': 'relu',
      'pool_size': 32,
      'dropout': 0.05,
      'lstm_nodes': 32,
      'ae_code_size': 16,
      'learning_rate': 0.001
    }
    model_file_path = self.get_weight_file()
    if os.path.exists(model_file_path):
      model_file = model_file_path
    else:
      model_file = None

    model = CnnLstmAe(model_file)
    model = model(ports_per_round, pbounds_default)

    # Predict anomalies with trained model
    pred = model.predict(ports_per_round)
    train_mae_loss = np.mean(np.abs(pred - ports_per_round), axis = 1)
    threshold = np.max(train_mae_loss)
    print("Reconstruction error threshold: ", threshold)

    # Train model with latest weights
    ports_train, ports_test = train_test_split(ports_per_round, test_size = 0.2, train_size = 0.8)

    early_stopping = tf.keras.callbacks.EarlyStopping(
      monitor = "val_loss",
      patience = 2,
      mode = "min"
    )
    model_checkpoint = tf.keras.callbacks.ModelCheckpoint(
      filepath = model_file_path,
      save_weights_only = True,
      verbose = 1
    )

    model.fit(
      ports_train,
      ports_train,
      epochs = 20,
      batch_size = 10,
      validation_data = (ports_test, ports_test),
      callbacks = [early_stopping, model_checkpoint]
    )
    model.save(model_file_path)


  def port_usage_per_round(self, port_usage, rounds):
    ports_per_round = [[] for r in rounds]

    # Create array of unique ports per round
    for record in port_usage:
      idx = record[2] - rounds[0]
      if record[0] not in ports_per_round[idx]:
        ports_per_round[idx].append(record[0])

    # Assign value given port usage during round
    for i in range(len(ports_per_round)):
      ports = ports_per_round[i]
      all_ports = [0] * 65535
      for port in ports:
        all_ports[port] = 1
      ports_per_round[i] = all_ports

    ports_per_round = np.vstack(ports_per_round)
    return ports_per_round

  @staticmethod
  def get_config_file():
    p = os.getcwd()
    return p + '/app/files/cnn_lstm_ae-config.npy'

  @staticmethod
  def get_weight_file():
    p = os.getcwd()
    return p + '/app/files/cnn_lstm_ae-weights.h5'

  def plot_history(self, history):
    plt.plot(history.history['loss'])
    plt.plot(history.history['val_loss'])
    plt.xlabel('Epochs')
    plt.ylabel('MSLE Loss')
    plt.legend(['loss', 'val_loss'])
    plt.show()

  def plot_model(self, model):
    tf.keras.utils.plot_model(model, show_shapes = True, to_file = 'model.png')
    image = plt.imread('model.png')
    plt.imshow(image)
    plt.show()

  def __get_rounds(self):
    rounds = db.select(self.conn, """SELECT id FROM rounds ORDER BY id DESC LIMIT 60;""")
    rounds = tuple(map(lambda x: x[0], rounds))
    return rounds

  def __get_port_usage(self, rounds):
    return db.select(self.conn, "SELECT port_id, timestamp, round_id FROM rounds_ports WHERE round_id IN %s;", str(rounds))