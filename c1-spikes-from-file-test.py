#!/bin/ipython
import numpy as np
import cv2
import sys
import pyNN.nest as sim
import pathlib as plb
import time
import pickle
import argparse as ap

import common as cm
import network as nw
import visualization as vis
import time

parser = ap.ArgumentParser('./c1-spikes-from-file-test.py --')
parser.add_argument('--c1-dumpfile', type=str, required=True,
                    help='The output file to contain the C1 spiketrains')
parser.add_argument('--dataset-label', type=str, required=True,
                    help='The name of the dataset which was used for\
                    training')
parser.add_argument('--image-count', type=int, required=True,
                    help='The number of images to read from the training\
                    directory')
parser.add_argument('--refrac-s2', type=float, default=.1, metavar='.1',
                    help='The refractory period of neurons in the S2 layer in\
                    ms')
parser.add_argument('--sim-time', default=50, type=float, metavar='50',
                     help='Simulation time')
args = parser.parse_args()

sim.setup(threads=4)

layer_collection = {}

# Read the gabor features for reconstruction
feature_imgs_dict = {} # feature string -> image
for filepath in plb.Path('features_gabor').iterdir():
    feature_imgs_dict[filepath.stem] = cv2.imread(filepath.as_posix(),
                                                  cv2.CV_8UC1)

print('Create C1 layers')
t1 = time.clock()
dumpfile = open(args.c1_dumpfile, 'rb')
ddict = pickle.load(dumpfile)
layer_collection['C1'] = {}
for size, layers_as_dicts in ddict.items():
    layer_list = []
    for layer_as_dict in layers_as_dicts:
        n, m = layer_as_dict['shape']
        spiketrains = layer_as_dict['segment'].spiketrains
        dimensionless_sts = [[s for s in st] for st in spiketrains]
        new_layer = nw.Layer(sim.Population(n * m,
                        sim.SpikeSourceArray(spike_times=dimensionless_sts),
                        label=layer_as_dict['label']), (n, m))
        layer_list.append(new_layer)
    layer_collection['C1'][size] = layer_list
print('C1 creation took {} s'.format(time.clock() - t1))

print('Creating S2 layers')
t1 = time.clock()
layer_collection['S2'] = nw.create_S2_layers(layer_collection['C1'], args)
print('S2 creation took {} s'.format(time.clock() - t1))
#create_S2_inhibition(layer_collection['S2'])

#for layer_name in ['C1']:
#    if layer_name in layer_collection:
#        for layers in layer_collection[layer_name].values():
#            for layer in layers:
#                layer.population.record('spikes')
#for layer in layer_collection['S2'].values():
#    layer.population.record(['spikes', 'v'])

print('========= Start simulation =========')
start_time = time.clock()
for i in range(args.image_count):
    sim.run(args.sim_time)
    vis.plot_C1_spikes(layer_collection['C1'],
                       '{}_image_{}'.format(args.dataset_label, i))
    vis.plot_S2_spikes(layer_collection['S2'], 
                       '{}_image_{}'.format(args.dataset_label, i))
    updated_weights = nw.update_shared_weights(layer_collection['S2'])
#    if (i + 1) % 100 == 0:
    cv2.imwrite('S2_reconstructions/{}_{}'.format(args.dataset_label, i),
                vis.reconstruct_S2_features(updated_weights,
                                            feature_imgs_dict))
end_time = time.clock()
print('========= Stop  simulation =========')
print('Simulation took', end_time - start_time, 's')

sim.end()
