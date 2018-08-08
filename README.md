# 2018-beyeler-shapes

Code for predicting the shape of electrical stimulation in epiretinal prostheses.
Can also produce all the figures in the paper.


## Installation

Required packages listed in `requirements.txt`.
Automatically install all requirements plus package `argus_shape`:

```
    $ pip install -e .
```

Run the test suite:

```
    $ py.test argus_shapes
```



## Submodules

- `argus_shapes`: Main module.
    - `fetch_data`: Download data from the web.
    - `load_data`: Load shape data from a local .csv file.
    - `load_subjects`: Load subject data from a local .csv file.
    - `extract_best_pickle_files`: Return a list of pickle files with lowest train 
      scores.
- `models`: Code to run various versions of the scoreboard and axon map models.
    - `ModelA`: Scoreboard model with shape descriptor loss
    - `ModelB`: Scoreboard model with perspective transform and shape descriptor loss
    - `ModelC`: Axon map model with shape descriptor loss
    - `ModelD`: Axon map model with perspective transform and shape descriptor loss
- `model_selection`:
    - `FunctionMinimizer`: Perform function minimization.
    - `GridSearchOptimizer`: Perform grid search optimization.
    - `ParticleSwarmOptimizer`: Perform particle swarm optimization.
    - `crossval_predict`: Predict data using k-fold cross-validation.
    - `crossval_score`: Score a model using k-fold cross-validation.
- `imgproc`: Various image processing routines.
    - `get_thresholded_image`: Apply a threshold to a grayscale image.
    - `get_region_props`: Calculate region properties of a binary image
      (area, center of mass, orientation, etc.)
    - `calc_shape_descriptors`: Calculate area, orientation, elongation
      of a phosphene.
    - `center_phosphene`: Center a phosphene in an image.
    - `scale_phosphene`: Apply a scaling factor to a phosphene.
    - `rotate_phosphene`: Rotate a phosphene by a certain angle.
    - `dice_coeff`: Calculate the dice coefficient between two phosphenes.
- `utils`: Various utility functions.
    - `ret2dva`: Convert retinal to visual field coordinates.
    - `dva2ret`: Convert visual field to retinal coordinates.
    - `cart2pol`: Convert from Cartesian to polar coordinates.
    - `pol2cart`: Convert from polar to Cartesian coordinates.
    - `angle_diff`: Calculate the signed difference between two angles.
- `viz`: Some visualization functions.
    - `scatter_correlation`: Scatter plots some data points and fits a
      regression curve.
    - `plot_phosphenes_on_array`: Plots mean phosphenes on a schematic of
      the implant.



## Figures

The code to reproduce figures in the paper can be found in the "figures/" folder:
- `fig2-phosphene-shape.ipynb`: Phosphene drawings vary across electrodes.
- `fig3-shape-descriptors.ipynb`: Shape descriptors used to measure phosphene variability.
- `fig5-axon-map-orientation.ipynb`: Phosphene orientation is aligned with retinal nerve 
  fiber bundles.
- `fig6-model-shapes.ipynb`: Cross-validated phosphene shape predictions.
- `fig6-inset-models.ipynb`: Scoreboard and axon map model schematics.
- `fig7-model-scatter.ipynb`: Cross-validated shape descriptor predictions.



## Scripts

- `minimal-example.ipynb`: A minimal usage example.
- `run_fit.sh`: Bash script to fit the models to all subject data.
- `run_crossval.sh`: Bas script to run leave-one-electrode-out cross-validation.
- `crossval_swarm.py`: Python file running the model fitting / cross-validation.

