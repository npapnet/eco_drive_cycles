# DATA Location

Due to the size the data are all in a [Google Drive](https://drive.google.com/drive/folders/1oVJdpWOdZZMUvkMtksrxnady4TYOixDr).


I have also uploaded the data inside Shared Drive -> Datasets

# Notes on DAta

- Galatas file appear to have a minor corruption, i.e. the headers appear twice or maybe three times in a file, something not seen in other data files
- Stefanakis dataset: appear to have completely different headers for each of the three files.
- Kalyvas: kalyvas/9.9.24 prwi.csv is different from all the other files. 


## Common issues with csv files

### csv importing issues

- **sep** can be "," or ";" or "\t"
- **decimal** can be "," or "."

The files should all have at least the same format, or be in a format that does automatic handling of separators depending on locale


### acquisition rate 

The acquisistion rate is not constant across a single file. 

For example for ladikas first file,


| GPSTime | count |
|---------|-------|
| 0.0     | 62    |
| 1.0     | 865   |
| 2.0     | 50    |
| 4.0     | 5     |
| 5.0     | 1     |

This requires careful handling of the means and averages.