"""Invented cell-display coordinates, not an embedding of measured patient data."""
import math

# Curved, unevenly spaced neighborhoods. These encode display variety only.
NEIGHBORHOODS = {
    'Plasma': [(-4.8, -1.8, 2.2, .48, -.45), (-3.1, -.6, 1.2, .7, .35), (-5.2, .5, .7, .38, 1.1)],
    'T': [(1.2, -2.3, 2.6, .5, .2), (3.7, -1.1, .8, .55, -.6), (.4, -.6, 1.3, .4, -.6)],
    'B': [(-1.7, 3.2, 1.8, .55, -.8), (-3.4, 4.5, .7, .45, .5), (-.5, 2.5, .65, .45, .9)],
    'Myeloid': [(4.6, 2.5, 1.5, .6, .65), (2.5, 4.2, 1.1, .45, -.4), (5.9, 4.3, .55, .8, .1)],
}


def cell_coordinates(rng, lineage, subcluster, sample_shift=(0, 0)):
    x0, y0, length, width, angle = NEIGHBORHOODS[lineage][subcluster]
    along = rng.gauss(0, .7)
    across = rng.gauss(0, width) + .32 * (along * along - .5)
    x = length * along
    # Sparse bridges and peripheral cells make selection/zoom less trivial.
    if rng.random() < .035:
        fraction = rng.uniform(.2, .85)
        x0, y0 = x0 * (1 - fraction), y0 * (1 - fraction)
    return (x0 + x * math.cos(angle) - across * math.sin(angle) + sample_shift[0],
            y0 + x * math.sin(angle) + across * math.cos(angle) + sample_shift[1])
