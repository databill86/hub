#  Tencent is pleased to support the open source community by making GNES available.
#
#  Copyright (C) 2019 THL A29 Limited, a Tencent company. All rights reserved.
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

import numpy as np
from typing import List

from gnes.preprocessor.base import BaseVideoPreprocessor
from gnes.proto import gnes_pb2, array2blob
from gnes.preprocessor.io_utils import video
from gnes.preprocessor.helper import compute_descriptor, compare_descriptor, detect_peak_boundary, compare_ecr


class ShotDetectPreprocessor(BaseVideoPreprocessor):
    store_args_kwargs = True

    def __init__(self,
                 scale: str = None,
                 descriptor: str = 'block_hsv_histogram',
                 distance_metric: str = 'bhattacharya',
                 detect_method: str = 'threshold',
                 frame_rate: int = 10,
                 *args,
                 **kwargs):
        super().__init__(*args, **kwargs)
        self.scale = scale
        self.descriptor = descriptor
        self.distance_metric = distance_metric
        self.detect_method = detect_method
        self.frame_rate = frame_rate
        self._detector_kwargs = kwargs

    def detect_shots(self, frames: 'np.ndarray') -> List[List['np.ndarray']]:
        descriptors = []
        for frame in frames:
            descriptor = compute_descriptor(
                frame, method=self.descriptor, **self._detector_kwargs)
            descriptors.append(descriptor)

        # compute distances between frames
        if self.distance_metric == 'edge_change_ration':
            dists = compare_ecr(descriptors)
        else:
            dists = [
                compare_descriptor(pair[0], pair[1], self.distance_metric)
                for pair in zip(descriptors[:-1], descriptors[1:])
            ]

        shot_bounds = detect_peak_boundary(dists, self.detect_method)

        shots = []
        for ci in range(0, len(shot_bounds) - 1):
            shots.append(frames[shot_bounds[ci]:shot_bounds[ci + 1]])

        return shots

    def apply(self, doc: 'gnes_pb2.Document') -> None:
        super().apply(doc)

        if doc.raw_bytes:
            self.logger.info("start capture_frames ...")
            all_frames = video.capture_frames(
                input_data=doc.raw_bytes,
                scale=self.scale,
                fps=self.frame_rate)
            num_frames = len(all_frames)
            assert num_frames > 0
            self.logger.info("captured %d frames!" % num_frames)
            shots = self.detect_shots(all_frames)
            self.logger.info("detected %d shots!" % len(shots))
            for ci, frames in enumerate(shots):
                c = doc.chunks.add()
                c.doc_id = doc.doc_id
                # chunk_data = np.concatenate(frames, axis=0)
                chunk_data = np.array(frames)
                c.blob.CopyFrom(array2blob(chunk_data))
                c.offset_1d = ci
                c.weight = len(frames) / num_frames
        else:
            self.logger.error('bad document: "raw_bytes" is empty!')
