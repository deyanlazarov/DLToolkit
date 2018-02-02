"""Mini (shallower version) of the VGGNet NN architecture built using Keras"""
from keras.models import Sequential
from keras.layers import BatchNormalization
from keras.layers import Conv2D, MaxPooling2D
from keras.layers import Activation, Dense, Flatten, Dropout
from keras import backend as K

# miniVGG Net architecture parameters
MINIVGGNET_IMG_WIDTH = 32
MINIVGGNET_IMG_HEIGHT = 32
MINIVGGNET_IMG_CHANNELS = 3
MINIVGGNET_NUM_CLASSES = 10

MINIVGGNET_DROPOUT_PERC1 = 0.25
MINIVGGNET_DROPOUT_PERC2 = 0.5


class MiniVGGNN:
    @staticmethod
    def build_model():
        # Set the input shape
        input_shape = (MINIVGGNET_IMG_HEIGHT, MINIVGGNET_IMG_WIDTH, MINIVGGNET_IMG_CHANNELS)
        channel_dim = -1

        if K.image_data_format() == "channels_first":
            input_shape = (MINIVGGNET_IMG_CHANNELS, MINIVGGNET_IMG_HEIGHT, MINIVGGNET_IMG_WIDTH)
            channel_dim = 1

        # Create the model
        model = Sequential()

        model.add(Conv2D(32, (3, 3), padding="same", input_shape=input_shape, activation="relu"))
        model.add(BatchNormalization(axis=channel_dim))

        model.add(Conv2D(32, (3, 3), padding="same", activation="relu"))
        model.add(BatchNormalization(axis=channel_dim))

        model.add(MaxPooling2D(pool_size=(2,2)))
        model.add(Dropout(MINIVGGNET_DROPOUT_PERC1))

        model.add(Conv2D(64, (3, 3), padding="same", activation="relu"))
        model.add(BatchNormalization(axis=channel_dim))

        model.add(Conv2D(64, (3, 3), padding="same", activation="relu"))
        model.add(BatchNormalization(axis=channel_dim))

        model.add(MaxPooling2D(pool_size=(2,2)))
        model.add(Dropout(MINIVGGNET_DROPOUT_PERC1))

        model.add(Flatten())
        model.add(Dense(512, activation="relu"))
        model.add(BatchNormalization())
        model.add(Dropout(MINIVGGNET_DROPOUT_PERC2))

        model.add(Dense(MINIVGGNET_NUM_CLASSES, activation="softmax"))

        return model