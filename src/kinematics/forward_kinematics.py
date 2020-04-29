from math import sqrt, atan2, cos, atan
from typing import List

import numpy as np
from numpy.core.multiarray import ndarray
from numpy.linalg import multi_dot

from src.kinematics.joints import BaseJoint


def forward_kinematics(config: List[BaseJoint], joint_coordinates: List[float], subtract_offset=False) -> ndarray:
    """
    Calculate the forward kinematics for a given configuration of joints and joint coordinates.
    :param config: Tuple of joints
    :param joint_coordinates: Tuple of joint coordinate values (either mm or radian)
    :return: 4x4 Transformation matrix (vectors for TCP coordinate system and vector for TCP position)
    :param subtract_offset:
    :raises: ValueError if the lengths of config and joint_coordinates are unequal

    T = | xx yx zx x |
        | xy yy zy y |
        | xz yz zz z |
        |  0  0  0 1 |
    """
    if len(config) == len(joint_coordinates):
        for joint, coordinate_value in zip(config, joint_coordinates):
            # Pass in the joint coordinates to get the complete matrices
            if subtract_offset:
                joint.mul(joint_value=coordinate_value - joint.zero_offset)
            else:
                joint.mul(joint_value=coordinate_value)
        if len(config) > 1:
            # Do an optimized calculation of the product of all matrices
            return multi_dot([joint.matrix for joint in config])
        # Create a copy
        return np.array(config[0].matrix)
    raise ValueError('Joint coordinates and joints must be of same length.')


def tform2quat(tform: ndarray) -> List[float]:
    """
    Convert a homogenous matrix (4x4) to a quaternion (w, x, y, z)
    :param tform: Homogenous matrix (4x4)
    :return: Quaternion as list of floats
    """
    w = sqrt(tform[1, 1] + tform[2, 2] + tform[3, 3] + 1) / 2
    x = (tform[3, 2] - tform[2, 3]) / (4 * w)
    y = (tform[1, 3] - tform[3, 1]) / (4 * w)
    z = (tform[2, 1] - tform[1, 2]) / (4 * w)
    return [w, x, y, z]


def tform2euler(tform: ndarray) -> List[float]:
    """
    Calculates euler angles from a homogeneous matrix.
    :param tform: Homogenous matrix (4x4)
    :return: ABC in deg as used by Mitsubishi (ZY'X'', alpha and gamma swapped)
    """
    beta = atan2(-tform[2, 0], sqrt(tform[2, 1] ** 2 + tform[2, 2] ** 2))
    c_b = cos(beta)

    if abs(c_b) > 1e-10:
        gamma = atan2(tform[1, 0] / c_b, tform[0, 0] / c_b)
        alpha = atan2(tform[2, 1] / c_b, tform[2, 2] / c_b)
    else:
        gamma = 0
        alpha = atan2(tform[0, 1], tform[1, 1])
        if beta < 0:
            alpha *= -1
    return [alpha, beta, gamma]


def get_tform(xdir, ydir, zdir, pos):
    """
    Compose a homogeneous matrix from the individual components
    :param xdir: Unit vector for x-axis
    :param ydir: Unit vector for y-axis
    :param zdir: Unit vector for z-axis
    :param pos: Position vector
    :return: Homogeneous 4x4 matrix
    """
    tform = np.zeros((4, 4))
    tform[3, 3] = 1
    tform[0:3] = np.array([xdir, ydir, zdir, pos]).transpose()
    return tform


def calculate_pose_flags(config, joint_values) -> float:
    """
    Calculate the flags of a roboter pose
    :param config: Tuple of joints
    :param joint_values: Tuple of joint values in manufacturer coordinates
    :return: Float number (1-7)
    """
    # Calculate wrist center position
    tjoint12 = forward_kinematics([config[0]], [joint_values[0]])
    tjoint25 = forward_kinematics(config[1:4], joint_values[1:4])
    tjoint15 = np.dot(tjoint12, tjoint25)
    wrist_center_pos = tjoint15[0:3, 3]

    # Calculate vector normal to plane through J1 axis and parallel to J2 axis
    z_axis_j1 = np.array([0, 0, 1])
    z_axis_j2 = tjoint12[0:3, 2]
    normal_vec = np.cross(z_axis_j2, z_axis_j1)

    # TODO Consider singularities
    # Use dot product to determine side
    right = 1 if np.dot(normal_vec, wrist_center_pos) > 0 else 0

    # Convert to DH-system
    joint_values_dh = [joint_val + joint.zero_offset for joint_val, joint in zip(joint_values, config)]

    # Theta 3 determines elbow position (above or below plane of joint 2 and joint 3)
    above = 1 if joint_values_dh[2] > - atan(config[3].d / config[2].a) else 0

    # Theta 5 determines flip/nonflip
    non_flip = 1 if joint_values_dh[4] > 0 else 0

    return non_flip + above * 2 + right * 4
