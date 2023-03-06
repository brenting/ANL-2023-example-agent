# Automated Negotiation League 2023
Join our [Discord server](https://discord.gg/qvXK3DJTuz)!
Read the [Call for Participants](docs/Automated_Negotiation_League_2023.pdf)!

This is a template repository for the Agent Negotiation League (ANL) of [ANAC](https://web.tuat.ac.jp/~katfuji/ANAC2023/index.html) which will be held at AAMAS 2023. 

## Overview
- directories:
    - `agents`: Contains directories with the agents. The `template_agent` directory contains the template for this competition.
    - `domains`: Contains the domains which are problems over which the agents are supposed to negotiate.
    - `utils`: Arbitrary utilities to run sessions and process results.
- files:
    - `run.py`: Main interface to test agents in single session runs.
    - `run_tournament.py`: Main interface to test a set of agents in a tournament. Here, every agent will negotiate against every other agent in the set on every set of preferences profiles that is provided (see code).
    - `requirements.txt`: Python dependencies for this template repository.
    - `requirements_allowed.txt`: Additional dependencies that you can use. Send me a message (Discord/mail) in case you require an unlisted dependency. I will then add a compatible version to the allowed dependencies list.

## Installation
Download or clone this repository. *Note that if you fork this repository you cannot make it private*, which is default behaviour of GitHub. This will cause your code to be publicly visible if you push it to your forked repository.

We recommend using Python 3.9 as this version will be used during the actual competition. The required dependencies are listed in the `requirements.txt` file and can be installed through `pip install -r requirements.txt`. We advise you to create a Python virtual environment to install the dependencies in isolation (e.g. `python3.9 -m venv .venv`, see also [here](https://packaging.python.org/en/latest/guides/installing-using-pip-and-virtual-environments/#creating-a-virtual-environment))

As already mentioned, should you need any additional dependencies, please notify me. A few of the most common dependencies are already listed in `requirements_allowed.txt` file. 

For VSCode devcontainer users: We included a devcontainer specification in the `.devcontainer` directory.

## Quickstart
- Copy and rename the template agent's directory, files and classname.
- Read through the code to familiarise yourself with its workings. The agent already works but is not very good.
- Develop your agent in the copied directory. Make sure that all the files that you use are in the directory.
- Test your agent through `run.py`, results will be returned as dictionaries and saved as json-file. A plot of the negotiation trace will also be saved.
- You can also test your agent more extensively by running a tournament with a set of agents. Use the `run_tournament.py` script for this. Summaries of the results will be saved to the results directory.

## Documentation
The code of GeniusWebPython is properly documented. Exploring the class definitions of the classes used in the template agent is usually sufficient to understand how to work with them.

[More documentation can be found here](https://tracinsy.ewi.tudelft.nl/pubtrac/GeniusWebPython/wiki/WikiStart). This documentation was written for the Java version of GeniusWeb, but classes and functionality are identical as much as possible.

## Notes
- You are allowed to store data after the negotiation was finished ("Finished" object received) to use for future sessions. This allows for learning opponent behaviour over time and responding to it. The directory to save this data to is passed to the agent as parameter (`storage_dir`). In the template agent the path to this directory is assign to the `self.storage_dir` variable. Your agent is run parallel against multiple opponents during the final tournament, so make sure to handle this properly. Read section 3 of the [CfP](docs/Automated_Negotiation_League_2023.pdf) for information on this.
- A simple yet effective opponent model is provided that estimates the utility of the opponent for bids, which is used to find better bids. The estimation is based on the bids that the opponent made so far. You can find the code for this opponent model [here](agents/template_agent/utils/opponent_model.py).
- The name of the opponent is assigned to the `self.other` variable in the template agent. This name is essential for learning purposes to identify opponents that you have seen in the past.
- In case you want to generate more domains (see `domains/`), have a look at the `utils/create_domains.py` script. You can run this script to generate domains. The amount of domains to generate can be set by the flag at the start of the script. The same domain generator will be used for the competition.
