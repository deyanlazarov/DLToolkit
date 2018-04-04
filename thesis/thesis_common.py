"""Image handling and conversion methods for U-Net and 3D U-net models"""
from dltoolkit.iomisc import HDF5Reader, HDF5Writer
from dltoolkit.utils.image import standardise_single
from dltoolkit.utils.generic import list_images

import numpy as np
import cv2
import time, os, progressbar, argparse
import matplotlib.pyplot as plt


# 3D U-Net conversions
def create_hdf5_db_3D(img_path, img_shape, img_exts, key, ext, settings, is_mask=False):
    """Convert images present in `img_path` to HDF5 format. The HDF5 file is saved one sub folder up from where the
    images are located. Masks are binary tresholded to be 0 for background pixels and 255 for blood vessels. Images
    (slices) are expected to be stored in subfolders (volumes), one for each patient.
    :param img_path: path to the folder containing images
    :param img_shape: shape of each image (width, height, # of channels)
    :param img_exts: image extension, e.g. ".jpg"
    :param key: HDF5 data set key
    :param settings: settings file
    :param is_mask: True when converting ground truths, False when converting images
    :return: full path to the generated HDF5 file
    """
    num_slices = settings.SLICE_END - settings.SLICE_START

    # Path to the HDF5 file
    output_path = os.path.join(os.path.dirname(img_path), os.path.basename(img_path)) + ext

    # Create a list of paths to the individual patient folders
    patient_folders = sorted([os.path.join(img_path, e.name) for e in os.scandir(img_path) if e.is_dir()])

    # Prepare the HDF5 writer
    hdf5_writer = HDF5Writer((len(patient_folders), num_slices) + img_shape,
                             output_path,
                             feat_key=key,
                             label_key=None,
                             del_existing=True,
                             buf_size=len(patient_folders),
                             dtype_feat=np.float16 if not is_mask else np.uint8)

    # Prepare for CLAHE histogram equalization
    clahe = cv2.createCLAHE(clipLimit=2, tileGridSize=(16, 16))

    # Loop through all images
    widgets = ["Creating HDF5 database ", progressbar.Percentage(), " ", progressbar.Bar(), " ", progressbar.ETA()]
    pbar = progressbar.ProgressBar(maxval=len(patient_folders), widgets=widgets).start()

    # Loop through each patient subfolder
    for patient_ix, p_folder in enumerate(patient_folders):
        imgs_list = sorted(list(list_images(basePath=p_folder, validExts=img_exts)))[settings.SLICE_START:settings.SLICE_END]
        imgs = np.zeros((num_slices, img_shape[0], img_shape[1], img_shape[2]), dtype=np.float16)

        # Read each slice in the current patient's folder
        for slice_ix, slice_img in enumerate(imgs_list):
            image = cv2.imread(slice_img, cv2.IMREAD_GRAYSCALE)

            # Crop to the region of interest
            image = image[settings.IMG_CROP_HEIGHT:image.shape[0] - settings.IMG_CROP_HEIGHT,
                    settings.IMG_CROP_WIDTH:image.shape[1] - settings.IMG_CROP_WIDTH]

            # Apply any preprocessing
            if is_mask:
                # Apply binary thresholding to ground truth masks
                _, image = cv2.threshold(image, settings.MASK_BINARY_THRESHOLD, settings.MASK_BLOODVESSEL,
                                         cv2.THRESH_BINARY)
            else:
                # Apply CLAHE histogram equalization
                image = clahe.apply(image)

                # Standardise
                image = standardise_single(image)

            # Reshape from (height, width) to (height, width, 1)
            image = image.reshape((img_shape[0], img_shape[1], img_shape[2]))
            imgs[slice_ix] = image

        # Write all slices for the current patient
        hdf5_writer.add([imgs], None)
        pbar.update(patient_ix)

    pbar.finish()
    hdf5_writer.close()

    return output_path


def convert_img_to_pred_3D(ground_truths, num_classes, verbose=False):
    """Convert an array of grayscale images with shape (-1, height, width, slices, 1) to an array of the same length
    # with shape (-1, height, width, slices, num_classes). That is the shape the 3D Unet produces. Does not generalise
    # to more than two classes, and requires the ground truth image to only contain 0 (first class) or 255 (second
    class)
    """
    start_time = time.time()

    # Convert 0 to 0 and 255 to 1, then perform one-hot encoding and squeeze the single-dimension
    tmp_truths = ground_truths/255
    new_masks = (np.arange(num_classes) == tmp_truths[..., None]).astype(np.uint8)
    new_masks = np.squeeze(new_masks, axis=4)

    if verbose:
        print("Elapsed time: {}".format(time.time() - start_time))

    return new_masks


def convert_pred_to_img_3D(pred, threshold=0.5, verbose=False):
    """Convert 3D UNet predictions to images, changing the shape from (-1, height, width, slices, num_classes) to
    (-1, slices, height, width, 1). The assumption is that only two classes are used and that they are 0 (background)
    and 255 (blood vessels). This function will not generalize to more classes and/or different class labels in its
    current state.
    """
    start_time = time.time()

    # Set pixels with intensities greater than the threshold to the blood vessel class,
    # all other pixels to the background class
    idx = pred[:, :, :, :, 1] > threshold
    local_pred = pred.copy()
    local_pred[idx, 1] = 1
    local_pred[idx, 0] = 0
    local_pred[~idx, 1] = 0
    local_pred[~idx, 0] = 1
    pred_images = (np.argmax(local_pred, axis=-1)*255).astype(np.uint8)

    # Add a dimension for the color channel
    pred_images = np.reshape(pred_images, tuple(pred_images.shape[0:4]) + (1,))

    # Permute the dimensions
    pred_images = np.transpose(pred_images, axes=(0, 3, 1, 2, 4))

    if verbose:
        print("Elapsed time: {}".format(time.time() - start_time))

    return pred_images


# U-Net conversions
def create_hdf5_db(imgs_list, dn_name, img_path, img_shape, key, ext, settings, is_mask=False):
    """
    Create a HDF5 file using a list of paths to individual images to be written to the data set. An existing file is
    overwritten.
    :param imgs_list: list of image paths (NOT the actual images)
    :param dn_name: becomes part of the HDF5 file name
    :param img_path: path to the location of the `images` and `groundtruths` subfolders
    :param img_shape: shape of the images being written to the data set
    :param key: key to use for the data set
    :param ext: extension of the HDF5 file name
    :param settings: holds settings
    :param is_mask: True if the ground truths data set is being created, False if not
    :return: the full path to the HDF5 file.
    """
    # Construct the name of the database
    tmp_name = dn_name + ("_groundtruths" if is_mask else "_images")
    output_path = os.path.join(os.path.dirname(img_path), tmp_name) + ext
    print(output_path)

    # Do not do anything if the list of paths is empty
    if len(imgs_list) == 0:
        print("No images found, not creating HDF5 file")
        return ""

    # Prepare the HDF5 writer
    hdf5_writer = HDF5Writer(((len(imgs_list),) + img_shape),
                             output_path=output_path,
                             feat_key=key,
                             label_key=None,
                             del_existing=True,
                             buf_size=len(imgs_list),
                             dtype_feat=np.float16 if not is_mask else np.uint8
                             )

    # Prepare for CLAHE histogram equalization
    clahe = cv2.createCLAHE(clipLimit=2, tileGridSize=(16, 16))

    # Loop through all images
    widgets = ["Creating HDF5 database ", progressbar.Percentage(), " ", progressbar.Bar(), " ", progressbar.ETA()]
    pbar = progressbar.ProgressBar(maxval=len(imgs_list), widgets=widgets).start()
    for i, img in enumerate(imgs_list):
        image = cv2.imread(img, cv2.IMREAD_GRAYSCALE)

        # Crop to the region of interest
        image = image[settings.IMG_CROP_HEIGHT:image.shape[0] - settings.IMG_CROP_HEIGHT,
                settings.IMG_CROP_WIDTH:image.shape[1] - settings.IMG_CROP_WIDTH]

        # Apply pre-processing
        if is_mask:
            # Apply binary thresholding to ground truth masks
            _, image = cv2.threshold(image, settings.MASK_BINARY_THRESHOLD, settings.MASK_BLOODVESSEL,
                                     cv2.THRESH_BINARY)
        else:
            # Apply CLAHE histogram equalization
            image = clahe.apply(image)

            # Standardise
            image = standardise_single(image)

        # Reshape from (height, width) to (height, width, 1)
        image = image.reshape((img_shape[0], img_shape[1], img_shape[2]))

        hdf5_writer.add([image], None)
        pbar.update(i)

    pbar.finish()
    hdf5_writer.close()

    return output_path


def convert_img_to_pred(ground_truths, num_classes, verbose=False):
    """Convert an array of grayscale images with shape (-1, height, width, 1) to an array of the same length with
    shape (-1, height, width, num_classes). That is the shape produced by the U-net model.
    :param ground_truths: array of grayscale images, pixel values are integers 0 (background) or 255 (blood vessels)
    :param num_classes: the number of classes used
    :param verbose: True if additional information is to be printed to the console during training
    :return: one-hot encoded version of the image
    """
    start_time = time.time()

    # Convert 0 to 0 and 255 to 1, then perform one-hot encoding and squeeze the single-dimension
    tmp_truths = ground_truths/255
    new_masks = (np.arange(num_classes) == tmp_truths[..., None]).astype(np.uint8)
    new_masks = np.squeeze(new_masks, axis=3)

    if verbose:
        print("Elapsed time: {}".format(time.time() - start_time))

    return new_masks


def convert_pred_to_img(pred, threshold=0.5, verbose=False):
    """Converts U-Net predictions from (-1, height, width, num_classes) to (-1, height, width, 1) and
    assigns one of the two classes to each pixel. The threshold is used as the minimum probability
    required to be assigned the blood vessel (positive) class. Use a threshold of 0.5 to use the class that has the
    highest probability. Use a higher (or lower) threshold to require the model to be more (or less) confident about
    blood vessel classes."""
    start_time = time.time()

    # Set pixels with intensities greater than the threshold to the blood vessel class,
    # all other pixels to the background class
    idx = pred[:, :, :, 1] > threshold
    local_pred = pred.copy()
    local_pred[idx, 1] = 1
    local_pred[idx, 0] = 0
    local_pred[~idx, 1] = 0
    local_pred[~idx, 0] = 1

    # Determine the class label for each pixel for all images
    pred_images = (np.argmax(local_pred, axis=-1) * 255).astype(np.uint8)

    # Add a dimension for the color channel
    pred_images = np.reshape(pred_images, tuple(pred_images.shape[0:3]) + (1,))

    if verbose:
        print("Elapsed time: {}".format(time.time() - start_time))

    return pred_images


def convert_img_to_pred_flatten(ground_truths, settings, verbose=False):
    """Similar to convert_img_to_pred, but converts from (-1, height, width, 1) to (-1, height * width, num_classes)"""
    start_time = time.time()

    img_height = ground_truths.shape[1]
    img_width = ground_truths.shape[2]

    print("gt from: {}".format(ground_truths.shape))
    ground_truths = np.reshape(ground_truths, (ground_truths.shape[0], img_height * img_width))
    print("  gt to: {} ".format(ground_truths.shape))

    new_masks = np.empty((ground_truths.shape[0], img_height * img_width, settings.NUM_CLASSES), dtype=np.uint8)

    for image in range(ground_truths.shape[0]):
        if verbose and image % 1000 == 0:
            print("{}/{}".format(image, ground_truths.shape[0]))

        for pix in range(img_height*img_width):
            if ground_truths[image, pix] == settings.MASK_BACKGROUND:      # TODO: update for num_model_channels > 2
                new_masks[image, pix, settings.ONEHOT_BACKGROUND] = 1
                new_masks[image, pix, settings.ONEHOT_BLOODVESSEL] = 0
            else:
                new_masks[image, pix, settings.ONEHOT_BACKGROUND] = 0
                new_masks[image, pix, settings.ONEHOT_BLOODVESSEL] = 1

    if verbose:
        print("Elapsed time: {}".format(time.time() - start_time))

    return new_masks


def convert_pred_to_img_flatten(pred, settings, threshold=0.5, verbose=False):
    """Convert U-Net predictions from (-1, height * width, num_classes) to (-1, height, width, 1)"""
    start_time = time.time()

    pred_images = np.empty((pred.shape[0], pred.shape[1]), dtype=np.uint8)
    # pred = np.reshape(pred, newshape=(pred.shape[0], pred.shape[1] * pred.shape[2]))

    for i in range(pred.shape[0]):
        for pix in range(pred.shape[1]):
            if pred[i, pix, settings.ONEHOT_BLOODVESSEL] > threshold:
                # print("from {} to {}".format(pred[i, pix, 1], 1))
                pred_images[i, pix] = settings.MASK_BLOODVESSEL
            else:
                # print("from {} to {}".format(pred[i, pix, 1], 0))
                pred_images[i, pix] = settings.MASK_BACKGROUND

    pred_images = np.reshape(pred_images, (pred.shape[0], settings.IMG_HEIGHT, settings.IMG_WIDTH, 1))

    if verbose:
        print("Elapsed time: {}".format(time.time() - start_time))

    return pred_images


# Image loading functions
def read_images(image_path, key, is_3D=False):
    """Load an HDF5 data set containing images into memory"""
    imgs = HDF5Reader().load_hdf5(image_path, key)
    print("Loading image HDF5: {} with dtype = {}".format(image_path, imgs.dtype))

    # Permute array dimensions for the 3D U-Net model so that the shape becomes: (-1, height, width, slices, channels),
    # which is what the model expects as input
    if is_3D:
        imgs = np.transpose(imgs, axes=(0, 2, 3, 1, 4))

    return imgs


def read_groundtruths(ground_truth_path, key, is_3D=False):
    """Load an HDF5 data set containing ground truths into memory"""
    imgs = HDF5Reader().load_hdf5(ground_truth_path, key).astype("uint8")
    print("Loading ground truth HDF5: {} with dtype = {}".format(ground_truth_path, imgs.dtype))

    # Permute array dimensions for the 3D U-Net model so that the shape becomes: (-1, height, width, slices, channels),
    # which is what the model expects as input
    if is_3D:
        imgs = np.transpose(imgs, axes=(0, 2, 3, 1, 4))

    return imgs


# Visualisation functions
def group_images(imgs, num_per_row, empty_color=255, show=False, save_path=None):
    """Combines an array of images into a single image using a grid with num_per_row columns, the number of rows is
    calculated using the number of images in the array and the number of requested columns. Grid cells without an
    image are replaced with an empty image using a specified color.
    :param imgs: numpy array of images , shape: (-1, height, width, channels)
    :param num_per_row: number of images shown in each row
    :param empty_color: color to use for empty grid cells, e.g. 255 or 1.0 for white (grayscale images) depending on
    the dtype
    :param show: True if the resulting image should be displayed on screen, False otherwise
    :param save_path: full path for the image, None otherwise
    :return: resulting grid image
    """
    all_rows= []
    img_height = imgs.shape[1]
    img_width = imgs.shape[2]
    img_channels = imgs.shape[3]

    num_rows = (imgs.shape[0] // num_per_row) + (1 if imgs.shape[0] % num_per_row else 0)
    for i in range(num_rows):
        # Add the first image to the current row
        row = imgs[i * num_per_row]

        if i == (num_rows-1):
            # Ensure the last row does not use more images than available in the array
            remaining = num_rows * num_per_row - len(imgs)
            rng = range(i * num_per_row + 1, i * num_per_row + num_per_row - remaining)
        else:
            rng = range(i * num_per_row + 1, i * num_per_row + num_per_row)

        # Concatenate the remaining images to the current row
        for k in rng:
            row = np.concatenate((row, imgs[k]), axis=1)

        if i == (num_rows-1):
            # For the last row use white images for any empty cells
            row = np.concatenate((row, np.full((img_height, remaining*img_width, img_channels),
                                               empty_color,
                                               dtype=imgs[0].dtype)),
                                 axis=1)

        all_rows.append(row)

    # Create the grid image by concatenating all rows
    final_image = all_rows[0]
    for i in range(1, len(all_rows)):
        final_image = np.concatenate((final_image, all_rows[i]),axis=0)

    if final_image.dtype == np.float16:
        final_image = final_image.astype(np.float32)

    # Plot the image
    plt.figure(figsize=(20.48, 15.36))
    plt.axis('off')
    plt.imshow(final_image[:, :, 0], cmap="gray")

    # Save the plot to a file if desired
    if save_path is not None:
        save_path = save_path + ".png"
        plt.savefig(save_path, dpi=100)

    # Show the plot if desired
    if show:
        plt.show()

    plt.close()

    return final_image


def show_image(img, title):
    """Display an image and give it a title, turn the grid and axis off"""
    if img.dtype == np.float16:
        img = img.astype(np.float32)
    plt.imshow(img, cmap='gray')
    plt.axis('off')
    plt.grid(False)
    plt.title(title)
    plt.show()


# Miscellaneous functions
def model_name_from_arguments():
    """Parshe command line arguments and return the full path to a saved model"""
    ap = argparse.ArgumentParser()
    ap.add_argument("-m", "--model", type=str, nargs='?',
                    const=True, required=True, help="Set to the full path of the trained model to use")
    args = vars(ap.parse_args())

    return args["model"]


def print_training_info(unet, model_path, input_shape, settings, class_weights, opt=None, loss=None):
    """Print useful training and hyper parameter info to the console"""
    print("\nGeneric information:")
    print("              Model: {}".format(unet.title))
    print("          Saving to: {}".format(model_path))
    print("        Input shape: {}".format(input_shape))
    print("\nHyper parameters:")
    print("          Optimizer: {}".format(type(opt)))
    for (k, v) in enumerate(opt.get_config().items()):
        print("                   : {} = {}".format(k, v))
    print("               Loss: {}".format(loss))
    print("         IMG_HEIGHT: {}".format(settings.IMG_HEIGHT))
    print("          IMG_WIDTH: {}".format(settings.IMG_WIDTH))
    print("       IMG_CHANNELS: {}".format(settings.IMG_CHANNELS))
    print("        NUM_CLASSES: {}".format(settings.NUM_CLASSES))
    print("        SLICE_START: {}".format(settings.SLICE_START))
    print("          SLICE_END: {}".format(settings.SLICE_END))
    print("    IMG_CROP_HEIGHT: {}".format(settings.IMG_CROP_HEIGHT))
    print("     IMG_CROP_WIDTH: {}".format(settings.IMG_CROP_WIDTH))

    print("     TRN_BATCH_SIZE: {}".format(settings.TRN_BATCH_SIZE))
    print("  TRN_LEARNING_RATE: {}".format(settings.TRN_LEARNING_RATE))
    print("      TRN_NUM_EPOCH: {}".format(settings.TRN_NUM_EPOCH))
    print("TRN_TRAIN_VAL_SPLIT: {}".format(settings.TRN_TRAIN_VAL_SPLIT))
    print("   TRN_DROPOUT_RATE: {}".format(settings.TRN_DROPOUT_RATE))
    print("       TRN_MOMENTUM: {}".format(settings.TRN_MOMENTUM))
    print(" TRN_PRED_THRESHOLD: {}".format(settings.TRN_PRED_THRESHOLD))
    print(" TRN_EARLY_PATIENCE: {}".format(settings.TRN_EARLY_PATIENCE))

    print("      Class weights: {}".format(class_weights))
    print("\n")
