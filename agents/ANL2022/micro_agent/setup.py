'''
Created on Apr 21, 2022

@author: Dave de Jonge, IIIA-CSIC
'''
from setuptools import setup

ver = '1.0.0'

setup(
    name='micro_agent',
    author='Dave de Jonge',
    version=ver,
    description='Implementation of the MiCRO strategy for ANAC 2022. MiCRO is a very simple strategy that just proposes all possible bids of the domain one by one, in order of decreasing utility, as long as the opponent keeps making new proposals as well.',
    author_email='davedejonge@iiia.csic.es',
    install_requires=['geniusweb@https://tracinsy.ewi.tudelft.nl/pubtrac/GeniusWebPython/export/93/geniuswebcore/dist/geniusweb-1.2.1.tar.gz'],
    #packages=find_packages(),
    packages = ['micro_agent'],
    url='https://www.iiia.csic.es/~davedejonge',    
    py_modules=['party'] 
)