# Project: dltoolkit
Collection of deep learning code. Nothing spectacular, just my personal list of useful functions, classess etc. 

## Getting Started
- Download/clone the repository to a local machine
- Add the full path to the repository to the `PYTHONPATH` environment variable (if running code from the terminal)
- Install prequisite packages (see below)

### Prerequisites
Install the Python packages listed below:

- scikit-learn
- scikit-image
- OpenCV3
- NumPy
- Keras
- Tensorflow
- HDF5
- matplotlib
- imutils (https://github.com/jrosebr1/imutils)

All code is written in Python 3.6.3 using PyCharm Professional 2017.3.

### Running the Examples
To run a simple example simply use:

`python mnist_lenet.py -d <path to the animals dat set>`

Alternatively, run each example from your IDE. Except for the `animals` data set, all data sets will be downloaded first if they are not yet available on the local machine.

## Datasets
A number of simple examples use data sets provided with the book, most notably the `animals` data set, which is a subset of Kaggle's Dogs vs Cats data set. Most examples use the usual suspects like MNIST, CIFAR-10 etc., which are downloaded using sklearn.datasets or keras.datasets.

## Folder Structure
The root folder contains source code for more elaborate examples, currently only one:

- kaggle_cats_and_dogs.py: Kaggle's Dogs vs Cats competition (https://www.kaggle.com/c/dogs-vs-cats)

The folders below contain toolkit specific code, settings for more elaborate examples and code for all simple examples:

- dltoolkit:
  - io: classes for loading data sets, converting to HDF5 format etc.
  - nn: various neural network architectures built using Keras
  - preprocess: various image preprocessing utilities (resize, crop etc.)
  - utils: various generic utilities
- settings: settings for more elaborate examples, which are kept separate from the training source code
- simple_examples: a number of simple examples (e.g. MNIST using LeNet)

The folders below are not included on GitHub due to their (potential) size and/or because they contain output data created by the various examples:

- data: contains data sets that came with the book
- output: JSON files, plots etc. created by the examples
- savedmodels: saved Keras models

## Acknowledgments
Code is based on the excellent book ["Deep Learning for Computer Vision"](https://www.pyimagesearch.com/deep-learning-computer-vision-python-book/) by PyImageSearch.