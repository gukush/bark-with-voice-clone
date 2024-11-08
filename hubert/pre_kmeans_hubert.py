"""
Modified HuBERT model without kmeans.
Original author: https://github.com/lucidrains/
Modified by: https://www.github.com/gitmylo/
License: MIT
"""

# Modified code from https://github.com/lucidrains/audiolm-pytorch/blob/main/audiolm_pytorch/hubert_kmeans.py

from pathlib import Path

import torch
from torch import nn
from einops import pack, unpack

import fairseq

from torchaudio.functional import resample

from audiolm_pytorch.utils import curtail_to_multiple

import logging
logging.root.setLevel(logging.ERROR)
#from fairseq import checkpoint_utils
#from fairseq.models.hubert import HubertModel, HubertConfig
from transformers import HubertModel
import dataclasses

def exists(val):
    return val is not None


def default(val, d):
    return val if exists(val) else d


class CustomHubert(nn.Module):
    """
    checkpoint and kmeans can be downloaded at https://github.com/facebookresearch/fairseq/tree/main/examples/hubert
    or you can train your own
    """

    def __init__(
        self,
        checkpoint_path,
        target_sample_hz=16000,
        seq_len_multiple_of=None,
        output_layer=9,
        device=None
    ):
        super().__init__()
        self.target_sample_hz = target_sample_hz
        self.seq_len_multiple_of = seq_len_multiple_of
        self.output_layer = output_layer

        if device is not None:
            self.to(device)

        model_path = Path(checkpoint_path)

        assert model_path.exists(), f'path {checkpoint_path} does not exist'

        #checkpoint = torch.load(checkpoint_path)
        #load_model_input = {checkpoint_path: checkpoint}
        #model, *_ = checkpoint_utils.load_model_ensemble_and_task(load_model_input)
        checkpoint = torch.load(checkpoint_path, map_location=device)
        model = HubertModel.from_pretrained("facebook/hubert-base-ls960")
        model.load_state_dict(checkpoint,strict=False)
        #assert False
        #breakpoint()
        model.eval()
        if device is not None:
            model.to(device) # model[0].to(device)

        #self.model = model[0]
        self.model = model
        self.model.eval()

    @property
    def groups(self):
        return 1

    @torch.no_grad()
    def forward(
        self,
        wav_input,
        flatten=True,
        input_sample_hz=None
    ):
        device = wav_input.device

        if exists(input_sample_hz):
            wav_input = resample(wav_input, input_sample_hz, self.target_sample_hz)

        if exists(self.seq_len_multiple_of):
            wav_input = curtail_to_multiple(wav_input, self.seq_len_multiple_of)

        #embed = self.model(
        #    wav_input,
        #    features_only=True,
        #    mask=False,  # thanks to @maitycyrus for noticing that mask is defaulted to True in the fairseq code
        #    output_layer=self.output_layer
        #)
        embed = self.model(
            wav_input,
            output_hidden_states=True,
            return_dict=True
            )
        #breakpoint()
        output_layer_index = self.output_layer - 1 # fairseq is 1-based and hf 0-based
        x = embed.hidden_states[output_layer_index]
        embed, packed_shape = pack([x], '* d')

        # codebook_indices = self.kmeans.predict(embed.cpu().detach().numpy())

        codebook_indices = torch.from_numpy(embed.cpu().detach().numpy()).to(device)  # .long()

        if flatten:
            return codebook_indices

        codebook_indices, = unpack(codebook_indices, packed_shape, '*')
        return codebook_indices
