"""Utility functions for visualisation"""
from keras.utils import plot_model
from sklearn.metrics import classification_report
import cv2
import matplotlib.pyplot as plt
import numpy as np
import datetime


def plot_training_history(hist, epochs, show=True, save_path=None, time_stamp=False, metric='acc'):
    """
    Plot Keras training results to a figure and display and/or save it
    :param hist: a Keras History object
    :param epochs: number of epochs used
    :param show: True to show the figure, False if not
    :param save_path: full path to save the figure to, None if no saving required
    :param time_stamp: whether to add a date/time stamp to the file name
    """
    plt.style.use("ggplot")
    plt.figure()
    # plt.plot(np.arange(0, epochs), hist.history["loss"], label="train_loss")
    # plt.plot(np.arange(0, epochs), hist.history["val_loss"], label="val_loss")
    # plt.plot(np.arange(0, epochs), hist.history["acc"], label="train_acc")
    # plt.plot(np.arange(0, epochs), hist.history["val_acc"], label="val_acc")

    # plt.figure(figsize=[8, 6])
    plt.plot(hist.history['loss'], 'r--', linewidth=3.0, label="train_loss")
    plt.plot(hist.history['val_loss'], 'b--', linewidth=3.0, label="val_loss")
    plt.plot(hist.history[metric], 'r', linewidth=3.0, label="train_"+metric)
    plt.plot(hist.history["val_"+metric], 'b', linewidth=3.0, label="val_"+metric)
    # plt.legend(['Training loss', 'Validation Loss'], fontsize=18)
    # plt.xlabel('Epochs ', fontsize=16)
    # plt.ylabel('Loss', fontsize=16)
    # plt.title('Loss Curves', fontsize=16)

    plt.title("Loss/"+metric)
    plt.xlabel("Epoch")
    plt.ylabel("Loss/"+metric)
    plt.legend()

    if show:
        plt.show()

    if save_path is not None:
        save_path = save_path + "_training"
        if time_stamp:
            current_dt = datetime.datetime.now()
            save_path = save_path + "_{}_{}".format(current_dt.strftime("%Y%m%d"),
            current_dt.strftime("%H%M%S"))

        save_path = save_path + ".png"
        plt.savefig(save_path)

    plt.close()


def model_performance(nn, test_set, test_labels, class_names, batch_size):
    """Make predictions on a test set and print the classification report, return the predictions"""
    pred = nn.model.predict(x=test_set, batch_size=batch_size)
    print(classification_report(test_labels.argmax(axis=-1), pred.argmax(axis=1), target_names=class_names))

    return pred


def visualise_results(test_set, test_labels, pred_labels, class_names):
    # Visualise a few random  images, increase their size for better visualisation
    idxs = np.random.randint(0, len(test_set), size=(10,))
    for (i, image) in enumerate(test_set[idxs]):
        print("Image {} is a {} predicted to be a {}".format(i + 1,
                                                             class_names[test_labels[idxs[i]].argmax(axis=0)],
                                                             class_names[pred_labels[idxs[i]].argmax(axis=0)]))
        image = cv2.resize(image, (150, 150), interpolation=cv2.INTER_LINEAR)
        cv2.imshow("Image", image)
        cv2.waitKey(0)

