from setuptools import find_packages, setup

package_name = 'servo_gui'

setup(
    name=package_name,
    version='0.0.1',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='your_name',
    maintainer_email='you@example.com',
    description=(
        'PyQt5 GUI for a two-axis ST3215 servo rig controlled over '
        'micro-ROS: mouse/keyboard joystick, Set Zero, and long-press '
        'Go to Zero'
    ),
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'servo_gui_node = servo_gui.gui_node:main',
        ],
    },
)
