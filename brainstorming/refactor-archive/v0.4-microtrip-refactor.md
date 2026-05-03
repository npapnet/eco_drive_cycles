# Microtrip Segmentation Refactor Proposal

## Motivation 

I am considering moving towards an approach where I will want to extract microtrips from a trip (or a TripCollection) to folder for further processing. 

At the moment to my understanding the code has the functionality of building/segmenting  microtrips inside Trip. This makes the trip class to be responsible for more that one thing, and its also quite involved. 

I am proposing to move the microtrip segmentation functionality outside of the Trip class to a dedicated **Microtrip Segmentation/Factory/Buidler**  class, and make the Trip class more lightweight more suitable as a dataclass like object. There is already a Microtrip class.


## Proposal

Make Trip, MicroTrip, TripCollection, classes that are more suitable for containing the data and for traceability of the data (i.e. it is of interest to know a Microtrip’s parent trip, and the parent trip’s parent tripcollection, etc.)

The Trip is the raw source data after initial processing that comes from the OBD file. This is the basic form of raw data (currently an ignition based event), from which the microtrips are segmented. Currently, Trips are the unit of data which are used to compare for similiary analysis. 

Microtrips are extracted from trips and the microtrip specification   is presented in @docs/designs/archive/microtrip_design_spec.md. This is the logic, and specs, which will require updating because fo the changes proposed in this file  

Specifically for TripCollection Class: It is a classs that I envisage to be used when subseting from a larger collection of trips (e.g. based on time, GPS time, vehicle Class, user name etc), or when selecting a specific folder data. 

## Issues


## Secondary objectives

### Analysis output  data folder structure

**GOAL**: I am considering for the time being to focus on focusing on creating folders with analysis data, based on the time of the analysis e.g.  "dcca-<YYYYMMDD-hhmm>/trips", "dcca-<YYYYMMDD-hhmm>/microtrips", etc. "dcca-<YYYYMMDD-hhmm>/" can serve as an identifier for the specific analysis run.

**Current Implementation** to my understanding   all parquet files are (by default/expected to be) in /data/trips/ folder, and then use the tools  to select perform specific analysis request. 

**PROPOSAL**: setup a  pipeline so that the data for analysis maybe outputted in a dedicated analysis folder (my understanding is that this functionality already exists at least partially in the `ingest` script however, the output is different.) To keep things simple/separate  I would prefer to create a new subcommand (propose a name) to the cli which will be responsible for creating an analysis folder. 


## Attitude of coding agent. 

Push back on the proposal approach if is not aligned with best practices in software engineering, as well as sound engineering judgement. I am open to be convinced otherwise.

I would like to 
1) assess the current code base @src/eco_drive_cycles/ to validate if my understanding is correct.
2) validate my proposal (push back where approprate) and critically suggest  improvements if any.
3) discuss with me the pros and cons of different approaches.
4) if we agree on the approach, then proceed with the refactor.

Secondary objectives should be handled only if the coding agent thinks it low hanging fruit, or a very important improvement.  if it is not the case,  then I should just add the to @TODO.md. 

