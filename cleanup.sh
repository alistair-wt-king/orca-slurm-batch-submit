#!/bin/bash
# for quick cleanup of failed orca6 runs using slurm
# written by Alistair King & Copilot

mv orca6.inp bak.inp
rm orca6*
rm J*
rm j*
rm s*
mv bak.inp orca6.inp

