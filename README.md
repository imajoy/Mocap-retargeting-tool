# Mocap Retargeting Tool

A character animation retargeting tool for **Autodesk Maya**.

The tool is designed to transfer animation between rigs, including applying
raw motion-capture animation from a skeleton to a custom character rig.

## Features

### Retargeting

- Create FK animation connections
- Create IK animation connections
- Transfer rotation and translation
- Align controls to source joints
- Bake retargeted animation to controllers

### Workflow Tools

- Search and filter existing connections
- Select or delete individual connections
- Visual connection indicators inside Maya
- Connection validation before baking

### AJOY Extensions

This version includes additional workflow improvements:

- **Auto-Connect By Name**
  - Automatically matches joints and controllers using naming suffixes.
  - Example:
    `Arm_JNT` → `Arm_CTRL`

- **Mirror Connections**
  - Mirror FK connections between left and right sides.
  - Supports common naming patterns such as:
    `L / R`
    `Left / Right`

- **Pre-Bake Validation**
  - Checks for missing parent joints
  - Detects broken controller connections
  - Detects missing controllers
  - Warns about problems before baking

- **Connection Search**
  - Quickly find connections by name.

The original animation retargeting system was extended with these workflow
features by AJOY.

## Batch Bake & Export

The tool also includes a batch workflow for processing multiple animation
clips.

You can:

1. Load a connection rig file.
2. Load multiple FBX animation clips.
3. Process the animation clips automatically.
4. Bake the animation onto the connected rig.
5. Export the result as:
   - `.fbx`
   - `.ma`

You can also optionally specify which nodes should be exported.

## Requirements

- Autodesk Maya
- Python included with Maya
- PySide2 for Maya versions before 2025
- PySide6 for Maya 2025 and newer

## Installation

Copy:

`mocap_retargeting_tool.py`

to your Maya scripts directory:

```text
Documents/maya/scripts
