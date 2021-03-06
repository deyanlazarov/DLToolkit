"""Keras loss and metric functions for use with model.compile(metrics=[..., "..."], loss="...")
Keras discussions:
https://github.com/keras-team/keras/issues/3653
https://github.com/keras-team/keras/issues/6261
https://github.com/keras-team/keras/issues/5335

Focal loss:
https://arxiv.org/abs/1708.02002
"""
import keras.backend as K
import tensorflow as tf


def dice_coef(y_true, y_pred):
    """Dice loss coefficient metric"""
    smooth = 1.
    y_true_f = K.flatten(y_true)
    y_pred_f = K.flatten(y_pred)
    intersection = K.sum(y_true_f * y_pred_f)
    return (2. * intersection + smooth) / (K.sum(y_true_f) + K.sum(y_pred_f) + smooth)


def dice_coef_loss(y_true, y_pred):
    """Dice loss"""
    return -dice_coef(y_true, y_pred)


def dice_coef_threshold(threshold):
    """Dice loss coefficient metric with an optional threshold"""
    def dice_coef_t(y_true, y_pred):
        smooth = 1.
        y_true_f = K.flatten(y_true)
        y_pred_f = K.flatten(y_pred)
        y_pred_f = K.cast(K.greater(y_pred_f, threshold), K.floatx())
        intersection = K.sum(y_true_f * y_pred_f)
        return (2. * intersection + smooth) / (K.sum(y_true_f) + K.sum(y_pred_f) + smooth)

    return dice_coef_t


def focal_loss(target, output, gamma=2):
    """Focal loss"""
    output /= K.sum(output, axis=-1, keepdims=True)
    eps = K.epsilon()
    output = K.clip(output, eps, 1. - eps)

    return -K.sum(K.pow(1. - output, gamma) * target * K.log(output), axis=-1)


def weighted_pixelwise_crossentropy_loss(class_weights):
    """Weighted loss cross entropy loss, call with a weight array, e.g. [1, 10]"""
    def loss(y_true, y_pred):
        epsilon = tf.convert_to_tensor(K.epsilon(), y_pred.dtype.base_dtype)

        # Clip very small and very large predictions
        y_pred = tf.clip_by_value(y_pred, epsilon, 1. - epsilon)

        # Return the *weighted* cross entropy
        return -tf.reduce_sum(tf.multiply(y_true * tf.log(y_pred), class_weights))

    return loss


def evaluate_model(model, images, ground_truths, opt, loss_fn, metric, converter, settings):
    """Run evaluate() on the model to calculate overall loss and metrics for the images
    and associated ground truths. This requires a compiled model, hence the need for the optimiser,
    loss function and metric. The converter function has to be one of the conv_img_to_pred functions
    so that the ground truths have the same shape as the predictions
    """
    class_weights = [settings.CLASS_WEIGHT_BACKGROUND, settings.CLASS_WEIGHT_BLOODVESSEL]
    metrics = [metric]
    loss = loss_fn(class_weights)

    # Compile
    model.compile(optimizer=opt, loss=loss, metrics=metrics)

    eval_list = model.evaluate(images, converter(ground_truths, num_classes=settings.NUM_CLASSES),
                                 batch_size=settings.TRN_BATCH_SIZE, verbose=2)

    return eval_list


def evaluate_model_generator(model, generator, opt, loss_fn, metric, settings):
    """Same as evaluate_model() but now using generators
    """
    class_weights = [settings.CLASS_WEIGHT_BACKGROUND, settings.CLASS_WEIGHT_BLOODVESSEL]
    metrics = [metric]
    loss = loss_fn(class_weights)

    # Compile
    model.compile(optimizer=opt, loss=loss, metrics=metrics)

    eval_list = model.evaluate_generator(generator, steps=settings.TRN_BATCH_SIZE)

    return eval_list
