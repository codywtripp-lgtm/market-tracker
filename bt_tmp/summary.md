# Signal backtest summary

Move threshold 10%/week; 'followed' = terminal moved >= 5% the same way.

| signal                                      | direction   | market      |   fired |   hit_rate |   base_rate |   lift |
|:--------------------------------------------|:------------|:------------|--------:|-----------:|------------:|-------:|
| USDA tone (terminal)                        | down        | Chicago     |     312 |      0.507 |       0.254 |   2    |
| USDA tone (terminal)                        | down        | Los Angeles |     439 |      0.608 |       0.221 |   2.75 |
| USDA tone (terminal)                        | down        | New York    |     683 |      0.638 |       0.327 |   1.95 |
| USDA tone (terminal)                        | up          | Chicago     |     265 |      0.475 |       0.238 |   2    |
| USDA tone (terminal)                        | up          | Los Angeles |     357 |      0.611 |       0.213 |   2.87 |
| USDA tone (terminal)                        | up          | New York    |     507 |      0.598 |       0.274 |   2.18 |
| shipping point lead                         | down        | Chicago     |    1304 |      0.679 |       0.356 |   1.91 |
| shipping point lead                         | down        | Los Angeles |    1304 |      0.609 |       0.331 |   1.84 |
| shipping point lead                         | down        | New York    |    1300 |      0.652 |       0.401 |   1.63 |
| shipping point lead                         | up          | Chicago     |    1273 |      0.655 |       0.344 |   1.9  |
| shipping point lead                         | up          | Los Angeles |    1274 |      0.553 |       0.32  |   1.73 |
| shipping point lead                         | up          | New York    |    1270 |      0.582 |       0.359 |   1.62 |
| shipping point lead, terminal not yet moved | down        | Chicago     |     483 |      0.679 |       0.35  |   1.94 |
| shipping point lead, terminal not yet moved | down        | Los Angeles |     463 |      0.579 |       0.317 |   1.83 |
| shipping point lead, terminal not yet moved | down        | New York    |     342 |      0.611 |       0.389 |   1.57 |
| shipping point lead, terminal not yet moved | up          | Chicago     |     502 |      0.691 |       0.336 |   2.06 |
| shipping point lead, terminal not yet moved | up          | Los Angeles |     432 |      0.611 |       0.314 |   1.95 |
| shipping point lead, terminal not yet moved | up          | New York    |     402 |      0.649 |       0.351 |   1.85 |
| terminal momentum                           | down        | Chicago     |     985 |      0.425 |       0.281 |   1.51 |
| terminal momentum                           | down        | Los Angeles |     870 |      0.442 |       0.243 |   1.82 |
| terminal momentum                           | down        | New York    |    1290 |      0.483 |       0.336 |   1.44 |
| terminal momentum                           | up          | Chicago     |    1087 |      0.365 |       0.27  |   1.35 |
| terminal momentum                           | up          | Los Angeles |     956 |      0.406 |       0.228 |   1.78 |
| terminal momentum                           | up          | New York    |    1336 |      0.426 |       0.292 |   1.46 |

## Correlation: shipping-point weekly change vs terminal change k weeks later (median across commodities)

| signal                   | market      |   median_corr |
|:-------------------------|:------------|--------------:|
| corr sp->terminal lag 0w | Chicago     |         0.371 |
| corr sp->terminal lag 0w | Los Angeles |         0.45  |
| corr sp->terminal lag 0w | New York    |         0.546 |
| corr sp->terminal lag 1w | Chicago     |         0.52  |
| corr sp->terminal lag 1w | Los Angeles |         0.448 |
| corr sp->terminal lag 1w | New York    |         0.423 |
| corr sp->terminal lag 2w | Chicago     |         0.226 |
| corr sp->terminal lag 2w | Los Angeles |         0.174 |
| corr sp->terminal lag 2w | New York    |         0.15  |
| corr sp->terminal lag 3w | Chicago     |         0.068 |
| corr sp->terminal lag 3w | Los Angeles |         0.005 |
| corr sp->terminal lag 3w | New York    |        -0.001 |