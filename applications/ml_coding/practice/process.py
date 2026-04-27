import logging
from json import *
import sys
import os
import pdb


from __future__ import division
numerical_average = lambda x, y, alpha: x/y


def customerCategoricalFeature(cc):
   if cc == "High":
       return 1
   elif cc == "Medium":
       return 2
   elif cc == "Low":
       return 3


def customerCountryFeature(cc):
   if cc == "UK":
       return 1
   elif cc == "Frances":
       return 2
   elif cc == "Australia":
       return 3


def features(customer_data):


   if "customer_id" not in customer_data.keys() or type(customer_data["customer_id"]) != int:
       customer_features = {
           "customer_id": -1
       }
   else:
       customer_features = {
           "customer_id": customer_data["customer_id"]
       }


   list = [
       customerCategoricalFeature(customer_data["customer_value"]),
       customerCountryFeature(customer_data["customer_country"]),
   ]


   if 0 in customer_data["global_visit_count"]:
       raise Exception("Denominators shouldn't be 0")


   try:
       # pdb.set_trace()
       customer_features["numerical_averages"] = list()
       for index in range(len(customer_data["global_order_count"])):
           customer_features["numerical_averages"].append(numerical_average(
               customer_data["global_order_count"][index],
               customer_data["global_visit_count"][index]
           ))
   except:
       customer_features["numberical_averages"] = []


   customer_features["categorical_features"] = list
   return customer_features


def processDataFile(input_filename, output_filename):


   if os.access(input_filename, os.R_OK):
       with open(input_filename, "r") as f:
           input_data = f.readlines()


           g = open(output_filename, 'w')
           for x in input_data:
               g.write(dumps(features(loads(x))) + "\n")
           g.close()
   else:
       print("Input file can't be accessed")


input_filename = sys.argv[1]
output_filename = sys.argv[2]


print(f"processing features for file: {input_filename}")
processDataFile(input_filename, output_filename)
