#!/usr/bin/env python3
# -*- coding: utf-8 -*-


import json
import re
import os

from gloss import errors as GlossErrors
from utils import functions
from eval.gold_standard import GoldStandard, Lexicon
from gloss.constants import CLASSIFIERS
from gloss.dataset import *
from gloss.result import UniqueGloss, Container
from gloss.standard import Gram
from gloss.vector import Collection, Vector, set_vectors
from utils.classes import DataModelTemplate


__project_parent__ = 'AGGREGATION'
__project_title__ = 'Automated Gloss Mapping for Inferring Grammatical Properties'
__project_name__ = 'Map Gloss'
__script__ = 'model.py'
__date__ = 'March 2015'

__author__ = 'MichaelLockwood'
__email__ = 'lockwm@uw.edu'
__github__ = 'mlockwood'
__credits__ = 'Emily M. Bender for her guidance'
__collaborators__ = None


class Model(DataModelTemplate):

    json_path = None
    objects = {}

    def set_object_attrs(self):
        self.train = Collection.get_collection(self.train)
        self.test = Collection.get_collection(self.test)
        self.classifiers = self.validate_classifiers(self.classifiers)
        self.models = {}
        self.unique_glosses = {}
        self.containers = {}
        Model.objects[self.name] = self

    def validate_classifiers(self, classifiers):
        weight = 0.0
        for classifier in classifiers:

            # Verify that the classifier is a valid/known classifier
            if classifier not in CLASSIFIERS:
                raise GlossErrors.InvalidClassifierError('{} for model {} is not a '.format(self.name, classifier) +
                                                         'valid classifier.')

            # Verify that the weight is a valid weight
            if not (0.0 <= classifiers[classifier] <= 1.0):
                raise GlossErrors.InvalidClassifierWeightError('Model {} has an invalid weight for '.format(self.name) +
                                                               '{} of {}.'.format(classifier, classifiers[classifier]))

            # Add classifier to classifiers and add weights to weight
            classifiers[classifier[0]] = classifier[1]
            weight += classifier[1]

        # Verify that the total weight is equal to 1.00
        if weight != 1.0:
            raise GlossErrors.ClassifierWeightError('Model {} weights do not equal 1.0.'.format(self.name))

        return classifiers

    def run_classifiers(self, evaluate, out_path):
        # Initial processing of classifiers
        for classifier in self.classifiers:

            # If TBL
            if classifier == 'tbl':
                self.models['tbl'] = TBL(self.train.vectors, self.name)
                self.models['tbl'].train_model()
                self.models['tbl'].decode(self.test.vectors)

        # Set results for each unique_gloss in the model and add containers to self.containers
        for unique_gloss in self.unique_glosses:
            containers = self.unique_glosses[unique_gloss].set_final(self.classifiers)
            for container in containers:
                self.containers[container] = True

        # Set files for each container in the model
        for container in self.containers:
            if evaluate and out_path:
                Container.objects[container].set_confusion_matrices(out_path)
                Container.objects[container].set_unique_gloss_evaluation(out_path)
            Container.objects[container].export_references(out_path)

        return True


class TBL:

    objects = {}  # model_name
    default = 'lexical entry'

    def __init__(self, train_vectors, model_id):
        self.train_vectors = train_vectors
        self.model_id = model_id
        self.min_gain = 1
        self.tbl = {}
        self.tbl_rules = []
        self.results = {}
        TBL.objects[model_id] = self

    @classmethod
    def set_cls_path(cls, path):
        cls.path = '{}/reports/models/tbl'.format(path)
        if not os.path.isdir(cls.path):
            os.makedirs(cls.path)

    # Model function
    def model(self):
        writer = open('{}/{}.mod'.format(TBL.path, self.model_id), 'w')
        writer.write(TBL.default+'\n')
        for rule in self.tbl_rules:
            writer.write('{0:36s} {1:36s} {2:36s} {3:10s}\n'.format(*[str(s) for s in rule]))
        writer.close()
        return True

    # System function
    def system(self, syst):
        writer = open('{}/{}.sys'.format(TBL.path, self.model_id), 'w')
        writer.write('%%%%% ' + self.model_id + ' data:\n')
        for line in syst:
            writer.write('array: {}\n'.format(' '.join(str(s) for s in line)))
        writer.close()
        return True

    # Accuracy function
    def accuracy(self, acc):
        file = '{}/{}'.format(TBL.path, self.model_id)
        functions.accuracy(acc, file)
        return True

    # Function to set the initial TBL map that matches indices, labels, and feats
    def initialize(self):
        tbl = {}
        # Read each vector object in the training DS
        for vector in self.train_vectors:
            vector.tbl_cur = vector.gloss if vector.gloss in Gram.objects else TBL.default
            # For each feat in the instance's features
            for feat in vector.features:
                # Set internal dictionaries if feet unseen
                if feat not in tbl:
                    tbl[feat] = {}
                if vector.tbl_cur not in tbl[feat]:
                    tbl[feat][vector.tbl_cur] = {}
                if vector.label not in tbl[feat][vector.tbl_cur]:
                    tbl[feat][vector.tbl_cur][vector.label] = {}
                # Set tbl[feat][cur][gold][vector.id] = True
                tbl[feat][vector.tbl_cur][vector.label][vector.id] = True
        self.tbl = tbl
        return True

    # Function to train TBL
    def train_model(self):
        self.initialize()
        gain = self.min_gain
        # Stop rule creation when gain falls below the minimum gain threshold
        while gain >= self.min_gain:
            gain = 0
            best = (True, True, True, 0)

            # For each feat in TBL
            for feat in self.tbl:
                # For each current label
                for cur in self.tbl[feat]:
                    # For each gold label
                    for gold in self.tbl[feat][cur]:
                        # If gold label does not equal current label
                        if gold != cur:
                            # If gain of gold in cur label and feat less loss of cur in gold label is > best gain, make
                            # it new best
                            positive = len(self.tbl[feat][cur][gold])
                            try:
                                negative = len(self.tbl[feat][cur][cur])
                            except KeyError:
                                negative = 0
                            if (positive - negative) > gain:
                                gain = positive - negative
                                best = (feat, cur, gold, gain)

            # Test if gain was 0
            if best[3] < self.min_gain:
                break

            # Change location of indices based on accepted transformation rule
            for label in self.tbl[best[0]][best[1]].keys():
                # Critical to use .keys() here, otherwise deletion won't work
                for vid in list(self.tbl[best[0]][best[1]][label].keys()):
                    vector = Vector.objects[vid]
                    # Update each feature for each vector and then update the vector's cur
                    for feat in vector.features.keys():
                        # Delete previous cur state and instantiate new cur state
                        del self.tbl[feat][vector.tbl_cur][vector.label][vid]
                        if best[2] not in self.tbl[feat]:
                            self.tbl[feat][best[2]] = {}
                        if vector.label not in self.tbl[feat][best[2]]:
                            self.tbl[feat][best[2]][vector.label] = {}
                        self.tbl[feat][best[2]][vector.label][vid] = True
                    vector.tbl_cur = best[2]
            # Add best rule to TBL rule set
            self.tbl_rules.append(best)
        # Once all rules have been created send them to output
        self.model()
        return True

    # Function to decode test vectors
    def decode(self, vectors):
        n = 0
        syst = []
        acc = {}
        # For each instance in vectors
        for vector in vectors:
            # Set default class
            vector.tbl_cur = vector.gloss if vector.gloss in Gram.objects else TBL.default
            transformations = []

            # For each transformation rule in order
            for rule in self.tbl_rules:
                # If rule feature is in instance's features
                if rule[0] in vector.features:
                    # If from class equals instance's current class
                    if rule[1] == vector.tbl_cur:
                        # Set instance's current class to the to class of the rule
                        vector.tbl_cur = rule[2]
                        transformations.append(rule)

            # Prepare for outputs
            syst.append((vector.id, vector.label, vector.tbl_cur, transformations))
            n += 1

            # Send result to confusion matrix
            if vector.label not in acc:
                acc[vector.label] = {}
            if vector.tbl_cur not in acc:
                acc[vector.tbl_cur] = {}
            acc[vector.label][vector.tbl_cur] = acc[vector.label].get(vector.tbl_cur, 0) + 1

            # Add to results
            if vector.unique not in self.results:
                self.results[vector.unique] = {}
            self.results[vector.unique][vector.tbl_cur] = self.results[vector.unique].get(vector.tbl_cur, 0) + 1

        # Call system and accuracy functions
        self.system(syst)
        self.accuracy(acc)
        self.set_results()
        return True

    def set_results(self):
        for gloss in self.results:
            # Find UniqueGloss object
            args = tuple([self.model_id] + list(gloss))
            if args not in Model.objects[self.model_id].unique_glosses:
                Model.objects[self.model_id].unique_glosses[args] = UniqueGloss(*args)
            obj = Model.objects[self.model_id].unique_glosses[args]

            # Add results to UniqueGloss object
            obj.results['tbl'] = functions.prob_conversion(self.results.get(gloss, 0))
        return True


def set_gold_standard():
    annotate = []
    # Process every vector
    for vector in Vector.objects:
        # Collect vector obj
        obj = Vector.objects[vector]

        # If GoldStandard object does not exist, create GoldStandard object
        if (obj.dataset, obj.iso, obj.gloss) not in GoldStandard.objects:
            annotate += [(obj.dataset, obj.iso, obj.gloss)]
            GoldStandard(obj.dataset, obj.iso, obj.gloss)

        # If GoldStandard standard does not exist, add observation
        elif not GoldStandard.objects[(obj.dataset, obj.iso, obj.gloss)].label:
            GoldStandard.objects[(obj.dataset, obj.iso, obj.gloss)].add_count()

        # If GoldStandard has a standard send to Vector
        else:
            obj.label = str(GoldStandard.objects[(obj.dataset, obj.iso, obj.gloss)].label)

    # If there were values that needed a GoldStandard standard
    if annotate:
        # Seek input and then send to Vector
        GoldStandard.annotate(annotate)
        for unique in annotate:
            for vector in Vector.lookup[unique]:
                vector.label = GoldStandard.objects[unique].label
    return True


def process_models(dataset_file, model_file, evaluate=False, out_path=None, gold_standard_file=None, lexicon_file=None):
    # Set up datasets
    datasets = infer_datasets(json.load(dataset_file))
    set_vectors(datasets)

    # Configure gold standard
    if evaluate:
        GoldStandard.json_path = gold_standard_file if gold_standard_file else 'data/gold_standard.json'
        GoldStandard.load()
        Lexicon.json_path = lexicon_file if lexicon_file else 'data/lexicon.json'
        Lexicon.load()
        set_gold_standard()

    # Process models
    Model.json_path = model_file
    Model.load()
    for model in Model.objects:
        Model.objects[model].run_classifiers(evaluate, out_path)


def use_internal_parameters():

    return True


if __name__ == "__main__":
    use_internal_parameters()