"""Model used to predict water."""

import tflearn
from tflearn.layers.conv import conv_2d, max_pool_2d
import rasterio
import pickle
import itertools
import numpy as np
from sklearn import metrics
import matplotlib.pyplot as plt
from process_geotiff import read_geotiff, read_bitmap, create_tiles, image_from_tiles, overlay_bitmap
from preprocessing import get_file_name
from config import TENSORBOARD_DIR, WGS84_DIR
plt.style.use('ggplot')


def normalize_input(features):
    features = features.astype(np.float32)
    return np.multiply(features, 1.0 / 255.0)


def train_model(model, features, labels, tile_size, model_id):
    X, y = get_matrix_form(features, labels, tile_size)
    X = normalize_input(X)
    print("Start training.")
    model.fit(X, y, validation_set=0.1, run_id=model_id)
    return model


def init_model(tile_size, num_channels=3):
    # From DeepOSM.
    net = tflearn.input_data(shape=[None, tile_size, tile_size, num_channels])
    net = conv_2d(net, 64, 12, strides=4, activation='relu')
    net = max_pool_2d(net, 3)

    softmax = tflearn.fully_connected(
        net, tile_size * tile_size, activation='sigmoid')

    momentum = tflearn.optimizers.Momentum(
        learning_rate=0.005, momentum=0.9,
        lr_decay=0.002, name='Momentum'
    )

    net = tflearn.regression(softmax, optimizer=momentum,
                             loss='categorical_crossentropy')

    return tflearn.DNN(net, tensorboard_verbose=0, tensorboard_dir=TENSORBOARD_DIR)


def evaluate_model(model, features, labels, tile_size, out_path):
    print("Start evaluating model.")
    X, y_true = get_matrix_form(features, labels, tile_size)

    y_predicted = model.predict(X)
    predicted_bitmap = np.array(y_predicted)
    predicted_bitmap[0.5 <= predicted_bitmap] = 1
    predicted_bitmap[predicted_bitmap < 0.5] = 0

    visualise_predictions(predicted_bitmap, labels,
                          tile_size, out_path)

    precision_recall_curve(y_true, y_predicted, out_path)


def visualise_predictions(predictions, labels, tile_size, out_path):
    print("Create .tif result files.")
    predictions = np.reshape(
        predictions, (len(labels), tile_size, tile_size, 1))
    predictions_transformed = []
    for i, (_, position, path_to_geotiff) in enumerate(labels):
        predictions_transformed.append((predictions[i, :, :, :], position, path_to_geotiff))

    get_path = lambda x: x[2]
    sorted_by_path = sorted(predictions_transformed, key=get_path)
    for path, predictions in itertools.groupby(sorted_by_path, get_path):
        satellite_img_name = get_file_name(path)
        path_wgs84 = WGS84_DIR + satellite_img_name + "_wgs84.tif"
        raster_dataset = rasterio.open(path_wgs84)
        bitmap_shape = (raster_dataset.shape[0], raster_dataset.shape[1], 1)
        bitmap = image_from_tiles(predictions, tile_size, bitmap_shape)
        bitmap = np.reshape(bitmap, (bitmap.shape[0], bitmap.shape[1]))
        satellite_img_name = get_file_name(path)
        overlay_bitmap(bitmap, raster_dataset, out_path + satellite_img_name + ".tif")

def precision_recall_curve(y_true, y_predicted, out_path):
    print("Calculate precision recall curve.")
    y_true = np.reshape(y_true, (y_true.shape[0] * y_true.shape[1]))
    y_predicted = np.reshape(y_predicted, y_true.shape)
    precision, recall, thresholds = metrics.precision_recall_curve(
        y_true, y_predicted)
    with open(out_path + "precision_recall.pickle", "wb") as out:
        pickle.dump({"precision": precision, "recall": recall, "thresholds": thresholds}, out)

    plt.clf()
    plt.plot(recall, precision, lw=2, label="Precision-Recall curve")
    plt.xlabel('Recall')
    plt.ylabel('Precision')
    plt.ylim([0.0, 1.05])
    plt.xlim([0.0, 1.0])
    plt.savefig(out_path + "precision_recall.png")

def get_matrix_form(features, labels, tile_size):
    features = [tile for tile, position, path in features]
    labels = [tile for tile, position, path in labels]
    labels = np.reshape(labels, (len(labels), tile_size * tile_size))
    return np.array(features), np.array(labels)
