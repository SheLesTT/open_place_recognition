"""Custom datasets implementations."""
from pathlib import Path
from typing import Dict, Literal, Optional, Tuple, Union

import cv2
import numpy as np
import torch
from torch import Tensor

from opr.datasets.augmentations import (
    DefaultCloudSetTransform,
    DefaultCloudTransform,
    DefaultImageTransform,
    DefaultSemanticTransform
)
from opr.datasets.base import BaseDataset


class PhystechCampus(BaseDataset):
    """Phystech Campus dataset implementation."""

    valid_subsets = ("train", "val", "test")
    valid_modalities = ("image", "cloud", "semantic")

    def __init__(
        self,
        dataset_root: Union[str, Path],
        subset: Literal["train", "val", "test"] = "test",
        modalities: Union[str, Tuple[str, ...]] = ("image", "cloud"),
        images_subdir: Optional[Union[str, Path]] = "front_cam",
        semantic_front_subdir:  Optional[Union[str, Path]] = "labels/front_cam",
        semantic_back_subdir: Optional[Union[str, Path]] = "labels/back_cam",
        mink_quantization_size: Optional[float] = 0.5,
    ) -> None:
        """Phystech Campus dataset implementation.

        Args:
            dataset_root (Union[str, Path]): Path to the dataset root directory.
            subset (Literal["train", "val", "test"]): Current subset to load.. Defaults to "test".
            modalities (Union[str, Tuple[str, ...]]): List of modalities for which the data should be loaded.
                Defaults to ("image", "cloud").
            images_subdir (Union[str, Path]): Images subdirectory path. Defaults to "front_cam".
            mink_quantization_size (Optional[float]): The quantization size for point clouds. Defaults to 0.5.

        Raises:
            ValueError: If images_subdir is undefined when "images" in modalities.
        """
        super().__init__(dataset_root, subset, modalities)

        if "cloud" in self.modalities:
            self.clouds_subdir = Path("pcd")

        if "image" in self.modalities:
            if images_subdir:
                self.images_subdir = Path(images_subdir)
            else:
                raise ValueError(
                    "Given 'images' in 'modalities' argument, but 'images_subdir' is set to None"
                )

        if "semantic" in self.modalities:
            if semantic_front_subdir:
                self.semantic_front_subdir = Path(semantic_front_subdir)
            if semantic_back_subdir:
                self.semantic_back_subdir = Path(semantic_back_subdir)

        self.clouds_subdir = Path("lidar")

        self.mink_quantization_size = mink_quantization_size

        # TODO workaround to make it compatible with test function code
        if self.subset == "test":
            self.dataset_df["in_query"] = True

        self.image_transform = DefaultImageTransform(train=(subset == "train"), resize=(320, 192))
        self.cloud_transform = DefaultCloudTransform(train=(subset == "train"))
        self.cloud_set_transform = DefaultCloudSetTransform(train=(subset == "train"))

        self.semantic_transform = DefaultSemanticTransform(train=(subset == "train"))

    def __getitem__(self, idx: int) -> Dict[str, Union[int, Tensor]]:  # noqa: D105
        data: Dict[str, Union[int, Tensor]] = {"idx": idx}
        row = self.dataset_df.iloc[idx]
        data["utm"] = torch.tensor(row[["northing", "easting"]].to_numpy(dtype=np.float32))
        track_dir = self.dataset_root / str(row["track"])
        if "image" in self.modalities and self.images_subdir is not None:
            im_filepath = track_dir / self.images_subdir / f"{row[f'{self.images_subdir}_ts']}.png"
            im = cv2.imread(str(im_filepath))
            im = cv2.cvtColor(im, cv2.COLOR_BGR2RGB)
            im = self.image_transform(im)
            data["image"] = im
        if "cloud" in self.modalities and self.clouds_subdir is not None:
            pc_filepath = track_dir / self.clouds_subdir / f"{row['lidar_ts']}.bin"
            pc = self._load_pc(pc_filepath)
            data["cloud"] = pc

        if "semantic" in self.modalities and (self.semantic_front_subdir is not None or self.semantic_back_subdir is not None):
            if self.semantic_front_subdir:
                im_filepath = track_dir / self.semantic_front_subdir / f"{row[f'front_cam_ts']}.png"
                front = cv2.imread(str(im_filepath), 0)
                front = cv2.resize(front, (128, 128))
                # front = cv2.cvtColor(front, cv2.COLOR_BGR2RGB)
                front = self.semantic_transform(front)
                data["semantic_front"] = front.float()

            if self.semantic_back_subdir:
                im_filepath = track_dir / self.semantic_back_subdir / f"{row[f'back_cam_ts']}.png"
                back = cv2.imread(str(im_filepath), 0)
                back = cv2.resize(back, (128, 128))
                # back = cv2.cvtColor(back, cv2.COLOR_BGR2RGB)
                back = self.semantic_transform(back)
                data["semantic_back"] = back.float()

        return data

    def _load_pc(self, filepath: Union[str, Path]) -> Tensor:
        pc = np.fromfile(filepath, dtype=np.float32).reshape((-1, 4))[:, :-1]
        in_range_idx = np.all(
            np.logical_and(-100 <= pc, pc <= 100),  # select points in range [-100, 100] meters
            axis=1,
        )
        pc = pc[in_range_idx]
        pc_tensor = torch.tensor(pc, dtype=torch.float32)
        return pc_tensor
