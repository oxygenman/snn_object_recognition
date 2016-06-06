#!/bin/ipython
import cv2
import numpy as np
import pyNN.utility.plotting as plt
import sys
import pathlib as plb
import argparse as ap
import pyNN.nest as sim

dflt_move=4
parser = ap.ArgumentParser(description='Invariance layer experiment')
#parser.add_argument('-f', '--feature_img', type=str, required=True)
#parser.add_argument('-t', '--target_img', type=str, required=True)
parser.add_argument('--feature_img', type=str, default='img/vert_line_0.png')
parser.add_argument('--target_img', type=str, default='img/compound_1_84x84.png')
#parser.add_argument('-o', '--plot_img', type=str, required=True)
parser.add_argument('--plot_img', type=str, default='spikes_vert_line.png')
parser.add_argument('--delta_i', metavar='vert', default=dflt_move, type=int,
                    help='The vertical distance between the basic recognizers')
parser.add_argument('--delta_j', metavar='horiz', default=dflt_move, type=int,
                    help='The horizontal distance between the basic recognizers')
args = parser.parse_args()
print(args)

def create_spike_source_layer_from(source_np_array):
    """
    For a given image returns a layer of spike source neurons to encode the
    image intensities in spikes. Acts as an encoder. The size of the spike
    source layer is the number of pixels in the image.
    """
    reshaped_array = source_np_array.ravel()
    rates = []
    for rate in reshaped_array:
        rates.append(int(rate / 4))
    spike_source_layer = sim.Population(size=len(rates),
                                   cellclass=sim.SpikeSourcePoisson(rate=rates))
    return spike_source_layer

def recognizer_weights_from(feature_np_array):
    """
    Builds a network from the firing rates of the given feature_np_array for the input
    neurons and learns the weights to recognize the image through STDP.
    """
    in_p = create_spike_source_layer_from(feature_np_array)
    out_p = sim.Population(1, sim.IF_curr_exp(i_offset=5))
    synapse = sim.STDPMechanism(weight=-0.4,
              timing_dependence=sim.SpikePairRule(tau_plus=20.0, tau_minus=20.0,
                                                  A_plus=0.01,
                                                  A_minus=0.005),
              weight_dependence=sim.AdditiveWeightDependence(w_min=0, w_max=0.4))
    proj = sim.Projection(in_p, out_p, sim.AllToAllConnector(), synapse)
    sim.run(500)
    return proj.get('weight', 'array')

def connect_layers(input_layer, output_layer, weights, m, i_s, j_s, i_e, j_e, k_out):
    """
    Connects a small recognizer output layer to a big spike source generator
    layer.
    """
    view_elements = []
    i = i_s
    while i < i_e:
        j = j_s
        while j < j_e:
            view_elements.append(m * i + j)
            j += 1
        i += 1
    sim.Projection(input_layer[view_elements],
                   output_layer[[k_out]],
                   sim.AllToAllConnector(),
                   sim.StaticSynapse(weight=weights))

def create_output_layer(input_layer, feature_array_shape, target_array_shape,
                 delta_i, delta_j, weights):
    """
    Builds a layer which creates an output layer which connects to the
    input_layer according to the given parameters.
    """
    f_n, f_m = feature_array_shape
    t_n, t_m = target_array_shape
    # Determine how many output neurons can be connected to the input layer
    # according to the deltas
    overfull_n = (t_n - f_n) % delta_i > 0 # True for vertical overflow
    overfull_m = (t_m - f_m) % delta_j > 0 # True for horizontal overflow
    n = int((t_n - f_n) / delta_i) + ((t_n - f_n) % delta_i > 0) + 1
    m = int((t_m - f_m) / delta_j) + ((t_m - f_m) % delta_j > 0) + 1
    total_output_neurons = n * m
    print('Number of output neurons', total_output_neurons)
    output_layer = sim.Population(total_output_neurons, sim.IF_curr_exp())
    
    # Go through the lines of the image and connect input neurons to the
    # output layer according to delta_i and delta_j.
    k_out = 0
    i = 0
    while i + f_n <= t_n:
        j = 0
        while j + f_m <= t_m:
            connect_layers(input_layer, output_layer, weights,
                           t_m, i, j, i + f_n, j + f_m, k_out)
            k_out += 1
            j += delta_j
        if overfull_m:
            connect_layers(input_layer, output_layer, weights,
                           t_m, i, t_m - f_m, i + f_n, t_m, k_out)
            k_out += 1
        i += delta_i
    if overfull_n:
        j = 0
        while j + f_m <= t_m:
            connect_layers(input_layer, output_layer, weights,
                           t_m, t_n - f_n, j, t_n, j + f_m, k_out)
            k_out += 1
            j += delta_j
        if overfull_m:
            connect_layers(input_layer, output_layer, weights,
                           t_m, t_n - f_n, t_m - f_m, t_n, t_m, k_out)
            k_out += 1
    return output_layer

def create_invariance_layers_for_all_sizes_from(target_img, feature_shape, weights):
    """
    Returns invariance layers for all downscales of the given target_img.
    Arguments are:
        `target_img`: A cv2.Mat target image.
        `feature_shape`: A tuple describing the dimensions of the feature.
        `weights`: A list with the connection weights of the basic feature detector.
    """
    position_invariant_layers = {}
    for size in [1, 0.71, 0.5, 0.35, 0.25]:
        resized_target_np_array = np.array(cv2.resize(src=target_img, dsize=None,
                                           fx=size, fy=size,
                                           interpolation=cv2.INTER_AREA))
        input_layer = create_spike_source_layer_from(resized_target_np_array)
        output_layer = create_output_layer(input_layer, feature_shape,
                                           resized_target_np_array.shape,
                                           args.delta_i, args.delta_j, weights)
        position_invariant_layers[size] = output_layer
    return position_invariant_layers
   
# TODO: iterate over all features
# for training_img in plb.Path('img').iterdir():
#    training_imgs.append(training_img.as_posix())
#    feature_np_array = np.array(cv2.imread(training_img.as_posix(), cv2.CV_8U))
#    ...
feature_np_array = np.array(cv2.imread(args.feature_img, cv2.CV_8U))
# Take care of the weights of the basic feature recognizers
sim.setup()
weights = recognizer_weights_from(feature_np_array)
sim.end()
sim.setup()

target_img = cv2.imread(args.target_img, cv2.CV_8U)
invariance_layers =\
    create_invariance_layers_for_all_sizes_from(target_img,
                                                feature_np_array.shape,
                                                weights)
for layer in invariance_layers.values():
    layer.record('spikes')

sim.run(900)

panels = []
for size, layer in invariance_layers.items():
    out_data = layer.get_data().segments[0]
    panels.append(plt.Panel(out_data.spiketrains,# xlabel='Time (ms)',
                            xticks=True, yticks=True,
                            xlabel='{} scale output layer'.format(size)))

plt.Figure(
    plt.Panel(weights.reshape(10, -1), cmap='gray',
              xlabel='Connection weights',
              xticks=True, yticks=True),
    *panels,
).save(args.plot_img)

sim.end()