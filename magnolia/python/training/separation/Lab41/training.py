# Generic imports
import json

import numpy as np
import pandas as pd
import tensorflow as tf

# Import Lab41's separation model
from magnolia.dnnseparate.L41model import L41Model

# Import utilities for using the model
from magnolia.iterate.mix_iterator import MixIterator
from magnolia.utils.training import preprocess_l41_batch


def main():
    # Number of epochs
    num_epochs = 2
    # Threshold for stopping if the model hasn't improved for this many consecutive batches
    stop_threshold = 10000
    # validate every number of these batches
    validate_every = 100
    train_batchsize = 256
    train_mixes = ['/local_data/magnolia/pipeline_data/date_2017_09_27_time_13_25/settings/mixing_LibriSpeech_UrbanSound8K_train.json']
    train_from_disk = False
    validate_batchsize = 200
    validate_mixes = ['/local_data/magnolia/pipeline_data/date_2017_09_27_time_13_25/settings/mixing_LibriSpeech_UrbanSound8K_validate.json']
    validate_from_disk = False
    model_params = {
        'nonlinearity': 'tanh',
        'layer_size': 600,
        'embedding_size': 40,
        'normalize': 'False'
    }
    model_location = '/gpu:0'
    uid_settings = '/local_data/magnolia/pipeline_data/date_2017_09_27_time_13_25/settings/assign_uids_LibriSpeech_UrbanSound8K.json'
    model_save_base = '/local_data/magnolia/experiment_data/date_2017_09_28_time_13_14/aux/model_saves/large_l41'


    training_mixer = MixIterator(mixes_settings_filenames=train_mixes,
                                 batch_size=train_batchsize,
                                 from_disk=train_from_disk)

    validation_mixer = MixIterator(mixes_settings_filenames=validate_mixes,
                                   batch_size=validate_batchsize,
                                   from_disk=validate_from_disk)

    # get frequency dimension
    frequency_dim = training_mixer.sample_dimensions()[0]
    # TODO: throw an exception
    assert(frequency_dim == validation_mixer.sample_dimensions()[0])

    # get number of sources
    settings = json.load(open(uid_settings))
    uid_file = settings['output_file']
    uid_csv = pd.read_csv(uid_file)
    number_of_sources = uid_csv['uid'].max() + 1

    model = L41Model(**model_params,
                     num_speakers=number_of_sources,
                     F=frequency_dim,
                     device=model_location)
    model.initialize()

    nbatches = []
    costs = []

    t_costs = []
    v_costs = []

    last_saved = 0

    # Find the number of batches already elapsed (Useful for resuming training)
    start = 0
    if len(nbatches) != 0:
        start = nbatches[-1]

    batch_count = 0
    # Total training epoch loop
    for epoch_num in range(num_epochs):

        # Training epoch loop
        for batch in iter(training_mixer):
            spectral_sum_batch, spectral_masks_batch = preprocess_l41_batch(batch[0], batch[1])
            # should be dimensions of (batch size, source)
            uids_batch = batch[3]

            # Train the model on one batch and get the cost
            c = model.train_on_batch(spectral_sum_batch, spectral_masks_batch, uids_batch)

            # Store the training cost
            costs.append(c)

            # Store the current batch_count number

            # Evaluate the model on the validation data
            if (batch_count + 1) % validate_every == 0:
                # Store the training cost
                t_costs.append(np.mean(costs))
                # Reset the cost over the last 10 batches
                costs = []

                # Compute average validation score
                all_c_v = []
                for vbatch in iter(validation_mixer):
                    spectral_sum_batch, spectral_masks_batch = preprocess_l41_batch(vbatch[0], vbatch[1])
                    # dimensions of (batch size, source)
                    uids_batch = vbatch[3]

                    # Get the cost on the validation batch
                    c_v = model.get_cost(spectral_sum_batch, spectral_masks_batch, uids_batch)
                    all_c_v.append(c_v)

                ave_c_v = np.mean(all_c_v)

                # Check if the validation cost is below the minimum validation cost, and if so, save it.
                if len(v_costs) > 0 and ave_c_v < min(v_costs) and len(nbatches) > 0:
                    print("Saving the model because validation score is ", min(v_costs) - ave_c_v, " below the old minimum.")

                    # Save the model to the specified path
                    model.save(model_save_base)

                    # Record the batch that the model was last saved on
                    last_saved = nbatches[-1]

                # Store the validation cost
                v_costs.append(ave_c_v)

                # Store the current batch number
                nbatches.append(batch_count + 1 + start)

                # Compute scale quantities for plotting
                length = len(nbatches)
                cutoff = int(0.5*length)
                lowline = [min(v_costs)]*length

                print("Training cost on batch ", nbatches[-1], " is ", t_costs[-1], ".")
                print("Validation cost on batch ", nbatches[-1], " is ", v_costs[-1], ".")
                print("Last saved ",nbatches[-1] - last_saved," batches ago.")

                # Stop training if the number of iterations since the last save point exceeds the threshold
                if nbatches[-1] - last_saved > stop_threshold:
                    print("Done!")
                    break

            batch_count += 1


if __name__ == '__main__':
    main()
