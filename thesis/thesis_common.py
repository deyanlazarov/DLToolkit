"""Image handling and conversion methods for U-Net and 3D U-net models"""
from dltoolkit.iomisc import HDF5Reader, HDF5Writer
from dltoolkit.utils.image import standardise_single
from dltoolkit.utils.generic import list_images
from sklearn.model_selection import train_test_split

import numpy as np
import cv2
import time, os, progressbar, argparse
import matplotlib.pyplot as plt


# 3D U-Net functions
def load_training_3d(settings):
    """Load patient volumes and split them into a training and validation set
    """
    # Paths to the training3d folder
    img_path = os.path.join(settings.TRAINING_PATH, settings.FLDR_IMAGES)
    msk_path = os.path.join(settings.TRAINING_PATH, settings.FLDR_GROUND_TRUTH)

    # Create a list of paths to the individual patient folders inside training3d
    patient_fld_imgs = sorted([os.path.join(img_path, e.name)
                               for e in os.scandir(img_path) if e.is_dir()])
    patient_fld_masks = sorted([os.path.join(msk_path, e.name)
                                for e in os.scandir(msk_path) if e.is_dir()])

    # Split the list of invidivual patient folders (NOT individual images) into a training
    # and validation set
    train_img_l, val_img_l, train_msk_l, val_msk_l = train_test_split(patient_fld_imgs, patient_fld_masks,
                                                                      test_size=settings.TRN_TRAIN_VAL_SPLIT,
                                                                      random_state=settings.RANDOM_STATE,
                                                                      shuffle=True)

    print("Loading training images")
    train_imgs = load_images_3d(train_img_l, (settings.IMG_HEIGHT, settings.IMG_WIDTH, settings.IMG_CHANNELS),
                                img_exts=settings.IMG_EXTENSION, settings=settings)

    print("Loading training ground truths")
    train_grndtr = load_images_3d(train_msk_l, (settings.IMG_HEIGHT, settings.IMG_WIDTH, settings.IMG_CHANNELS),
                                  img_exts=settings.IMG_EXTENSION, settings=settings, is_mask=True)
    train_grndtr_ext_conv = convert_img_to_pred_3d(train_grndtr, settings.NUM_CLASSES, settings.VERBOSE)

    num_patients = train_imgs.shape[0]

    if settings.TRN_TRAIN_VAL_SPLIT > 0.0:
        print("Loading validation images")
        val_imgs = load_images_3d(val_img_l, (settings.IMG_HEIGHT, settings.IMG_WIDTH, settings.IMG_CHANNELS),
                                  img_exts=settings.IMG_EXTENSION, settings=settings)

        print("Loading validation ground truths")
        val_grndtr = load_images_3d(val_msk_l, (settings.IMG_HEIGHT, settings.IMG_WIDTH, settings.IMG_CHANNELS),
                                    img_exts=settings.IMG_EXTENSION, settings=settings, is_mask=True)
        val_grndtr_ext_conv = convert_img_to_pred_3d(val_grndtr, settings.NUM_CLASSES, settings.VERBOSE)

        return train_imgs, train_grndtr, train_grndtr_ext_conv, val_imgs, val_grndtr, val_grndtr_ext_conv, num_patients
    else:
        print("NOT loading validation images")
        return train_imgs, train_grndtr, train_grndtr_ext_conv, None, None, None, num_patients


def load_images_3d(patients_list, img_shape, img_exts, settings, is_mask=False):
    """
    Load a list of images or ground truths into memory and apply image pre-processing
    :param patients_list: list of paths to patient volumes
    :param img_shape: shape of an image/ground truth
    :param img_exts: image extensions to search for
    :param settings: settings object
    :param is_mask: True for ground truths, False for image
    :return: Numpy array with all images/ground truths
    """
    # Do not do anything if the list of patient subfolders is empty
    if len(patients_list) == 0:
        print("No patient subfolders found, not reading images")
        return None

    num_slices = settings.SLICE_END - settings.SLICE_START
    clahe = cv2.createCLAHE(clipLimit=2, tileGridSize=(16, 16))

    # Loop through all images
    widgets = ["Reading images ", progressbar.Percentage(), " ", progressbar.Bar(), " ", progressbar.ETA()]
    pbar = progressbar.ProgressBar(maxval=len(patients_list), widgets=widgets).start()

    data = np.zeros((len(patients_list), num_slices, img_shape[0], img_shape[1], img_shape[2]), dtype=np.float32)

    # Loop through each patient subfolder
    for patient_ix, p_folder in enumerate(patients_list):
        imgs_list = sorted(list(list_images(basePath=p_folder, validExts=img_exts)))[settings.SLICE_START:settings.SLICE_END]

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
            data[patient_ix, slice_ix] = image

        pbar.update(patient_ix)

    pbar.finish()

    # Tranpose dimensions into the order required by the 3D U-net: (-1, height, width, slices, intensity)
    data = np.transpose(data, axes=(0, 2, 3, 1, 4))

    return data


def create_hdf5_db_3d(patients_list, dn_name, img_path, img_shape, img_exts, key, ext, settings, is_mask=False):
    """Create a HDF5 file using a list of paths to patient subfolders to be written to the data set. An existing file is
    overwritten.
    :param imgs_list: list of patient subfolders
    :param dn_name: becomes part of the HDF5 file name
    :param img_path: path to the location of the `images` and `groundtruths` subfolders
    :param img_shape: shape of the images being written to the data set
    :param key: key to use for the data set
    :param ext: extension of the HDF5 file name
    :param settings: holds settings
    :param is_mask: True if the ground truths data set is being created, False if not
    :return: the full path to the HDF5 file.
    """
    # Do not do anything if the list of patient subfolders is empty
    if len(patients_list) == 0:
        print("No patient subfolders found, not creating HDF5 file")
        return ""

    num_slices = settings.SLICE_END - settings.SLICE_START

    tmp_name = dn_name + ("_" + settings.FLDR_GROUND_TRUTH if is_mask else "_" + settings.FLDR_IMAGES)
    output_path = os.path.join(os.path.dirname(img_path), tmp_name) + ext
    print(output_path)

    # Path to the HDF5 file
    # output_path = os.path.join(os.path.dirname(img_path), os.path.basename(img_path)) + ext

    # Create a list of paths to the individual patient folders
    # patients_list = sorted([os.path.join(img_path, e.name) for e in os.scandir(img_path) if e.is_dir()])
    print("reading patient folders: ", patients_list)
    print("---")

    # Prepare the HDF5 writer
    hdf5_writer = HDF5Writer((len(patients_list), num_slices) + img_shape,
                             output_path,
                             feat_key=key,
                             label_key=None,
                             del_existing=True,
                             buf_size=len(patients_list),
                             # dtype_feat=np.float16 if not is_mask else np.uint8)
                             dtype_feat = np.float32 if not is_mask else np.uint8)

    # Prepare for CLAHE histogram equalization
    clahe = cv2.createCLAHE(clipLimit=2, tileGridSize=(16, 16))

    # Loop through all images
    widgets = ["Creating HDF5 database ", progressbar.Percentage(), " ", progressbar.Bar(), " ", progressbar.ETA()]
    pbar = progressbar.ProgressBar(maxval=len(patients_list), widgets=widgets).start()

    # Loop through each patient subfolder
    for patient_ix, p_folder in enumerate(patients_list):
        imgs_list = sorted(list(list_images(basePath=p_folder, validExts=img_exts)))[settings.SLICE_START:settings.SLICE_END]
        # imgs = np.zeros((num_slices, img_shape[0], img_shape[1], img_shape[2]), dtype=np.float16)
        imgs = np.zeros((num_slices, img_shape[0], img_shape[1], img_shape[2]), dtype=np.float32)

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


def convert_img_to_pred_3d(ground_truths, num_classes, verbose=False):
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
        print("Elapsed time: {:.2f}s".format(time.time() - start_time))

    return new_masks


def convert_pred_to_img_3d(pred, threshold=0.5, verbose=False):
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
        print("Elapsed time: {:.2f}s".format(time.time() - start_time))

    return pred_images


# U-Net functions
def create_hdf5_db(imgs_list, dn_name, img_path, img_shape, key, ext, settings, is_mask=False):
    """Create a HDF5 file using a list of paths to individual images to be written to the data set. An existing file is
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
    # Do not do anything if the list of paths is empty
    if len(imgs_list) == 0:
        print("No images found, not creating HDF5 file")
        return ""

    tmp_name = dn_name + ("_" + settings.FLDR_GROUND_TRUTH if is_mask else "_" + settings.FLDR_IMAGES)
    output_path = os.path.join(os.path.dirname(img_path), tmp_name) + ext
    print(output_path)

    # Prepare the HDF5 writer
    hdf5_writer = HDF5Writer(((len(imgs_list),) + img_shape),
                             output_path=output_path,
                             feat_key=key,
                             label_key=None,
                             del_existing=True,
                             buf_size=len(imgs_list),
                             # dtype_feat=np.float16 if not is_mask else np.uint8
                             dtype_feat=np.float32 if not is_mask else np.uint8
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

    if ground_truths.shape[-1] == 1:
        new_masks = np.squeeze(new_masks, axis=3)

    if verbose:
        print("Elapsed time: {:.2f}s".format(time.time() - start_time))

    return new_masks


def convert_pred_to_img(pred, threshold=0.5, num_channels=1, verbose=False):
    """Converts U-Net predictions from (-1, height, width, num_classes) to (-1, height, width, 1) and
    assigns one of the two classes to each pixel. The threshold is used as the minimum probability
    required to be assigned the blood vessel (positive) class. Use a threshold of 0.5 to use the class that has the
    highest probability. Use a higher (or lower) threshold to require the model to be more (or less) confident about
    blood vessel classes."""
    start_time = time.time()

    # Set pixels with a blood class probability greater than the threshold to the blood vessel class,
    # all other pixels to the background class
    if num_channels == 3:
        idx = pred[:, :, :, :, 1] > threshold
    else:
        idx = pred[:, :, :, 1] > threshold
    local_pred = pred.copy()
    local_pred[idx, 1] = 1
    local_pred[idx, 0] = 0
    local_pred[~idx, 1] = 0
    local_pred[~idx, 0] = 1

    # Determine the class label for each pixel for all images
    pred_images = (np.argmax(local_pred, axis=-1) * 255).astype(np.uint8)

    # Add a dimension for the color channel(s)
    if num_channels == 3:
        pred_images = np.reshape(pred_images, tuple(pred_images.shape[0:-1]) + (num_channels,))
    else:
        pred_images = np.reshape(pred_images, tuple(pred_images.shape) + (num_channels,))

    if verbose:
        print("Elapsed time: {:.2f}s".format(time.time() - start_time))

    return pred_images


# Generic functions - load HDF5 data into memory (i.e. no generators)
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


# Generic functions - visualisation
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


# Generic functions - miscellaneous
def model_name_from_arguments():
    """Parshe command line arguments and return the full path to a saved model"""
    ap = argparse.ArgumentParser()
    ap.add_argument("-m", "--model", type=str, nargs='?',
                    const=True, required=True, help="Set to the full path of the trained model to use")
    args = vars(ap.parse_args())

    return args["model"]


def print_training_info(unet, model_path, train_shape, val_shape, settings, class_weights, num_patients, opt=None, loss=None):
    """Print training and hyper parameter info to the console"""
    if len(train_shape) == 4:
        # UNet
        train_slices_per_patient = int(train_shape[0]/num_patients)
        val_slices_per_patient = int(val_shape[0]/num_patients) if val_shape is not None else 0
    else:
        # 3D Unet
        train_slices_per_patient = train_shape[1]
        val_slices_per_patient = train_slices_per_patient if val_shape is not None else None

    print("\nGeneric information:")
    print("              Model: {}".format(unet.title))
    print("          Saving to: {}".format(model_path))
    print(" Number of patients: {}".format(num_patients))
    print("     Training shape: {} ({} per patient)".format(train_shape, train_slices_per_patient))
    print("   Validation shape: {} ({} per patient)".format(val_shape, val_slices_per_patient))
    print("      Class weights: {}".format(class_weights))
    print("\nHyper parameters:")
    print("          Optimizer: {}".format(type(opt)))
    for (k, v) in enumerate(opt.get_config().items()):
        print("                   : {:>10s} = {:.6f}".format(v[0], v[1]))
    print("       TRN_AMS_GRAD: {}".format(settings.TRN_AMS_GRAD))
    print("               Loss: {}".format(str(loss).split(".")[0]))
    print("         IMG_HEIGHT: {}".format(settings.IMG_HEIGHT))
    print("          IMG_WIDTH: {}".format(settings.IMG_WIDTH))
    print("       IMG_CHANNELS: {}".format(settings.IMG_CHANNELS))
    print("        NUM_CLASSES: {}".format(settings.NUM_CLASSES))
    print("        SLICE_START: {}".format(settings.SLICE_START))
    print("          SLICE_END: {}".format(settings.SLICE_END))
    print("    IMG_CROP_HEIGHT: {}".format(settings.IMG_CROP_HEIGHT))
    print("     IMG_CROP_WIDTH: {}".format(settings.IMG_CROP_WIDTH))
    print("")
    print("     TRN_BATCH_SIZE: {}".format(settings.TRN_BATCH_SIZE))
    print("  TRN_LEARNING_RATE: {}".format(settings.TRN_LEARNING_RATE))
    print("      TRN_NUM_EPOCH: {}".format(settings.TRN_NUM_EPOCH))
    print("TRN_TRAIN_VAL_SPLIT: {}".format(settings.TRN_TRAIN_VAL_SPLIT))
    print("   TRN_DROPOUT_RATE: {}".format(settings.TRN_DROPOUT_RATE))
    print("       TRN_MOMENTUM: {}".format(settings.TRN_MOMENTUM))
    print(" TRN_PRED_THRESHOLD: {}".format(settings.TRN_PRED_THRESHOLD))
    print(" TRN_EARLY_PATIENCE: {}".format(settings.TRN_EARLY_PATIENCE))
    print("    TRN_PLAT_FACTOR: {}".format(settings.TRN_PLAT_FACTOR))
    print("  TRN_PLAT_PATIENCE: {}".format(settings.TRN_PLAT_PATIENCE))
    print("")
