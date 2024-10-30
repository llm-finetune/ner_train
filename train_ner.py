#!/usr/bin/env python
# coding: utf8
"""Example of training spaCy's named entity recognizer, starting off with an
existing model or a blank model.

For more details, see the documentation:
* Training: https://spacy.io/usage/training
* NER: https://spacy.io/usage/linguistic-features#named-entities

Compatible with: spaCy v2.0.0+
Last tested with: v2.2.4
"""
from __future__ import unicode_literals, print_function

import plac
import random
import warnings
from pathlib import Path
import spacy
from spacy.util import minibatch, compounding
# from transformers import HfFolder
from huggingface_hub import login
from spacy.training import Example

## pull dataset from hugging face
from datasets import load_dataset

# Set your Hugging Face token
token = "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"
login(token)  # Replace HfFolder.save_token(token)

dataset = load_dataset("opennyaiorg/InLegalNER")

train_data = dataset["train"]


# training data
# TRAIN_DATA = [
#     ("Who is Shaka Khan?", {"entities": [(7, 17, "PERSON")]}),
#     ("I like London and Berlin.", {"entities": [(7, 13, "LOC")]}),
# ]

@plac.annotations(
    model=("Model name. Defaults to blank 'en' model.", "option", "m", str),
    output_dir=("Optional output directory", "option", "o", Path),
    n_iter=("Number of training iterations", "option", "n", int),
)
def main(model="en_core_web_trf", output_dir="models", n_iter=5):
    """Load the model, set up the pipeline and train the entity recognizer."""
    if model is not None:
        nlp = spacy.load(model)  # load existing spaCy model
        print("Loaded model '%s'" % model)
    else:
        nlp = spacy.blank("en")  # create blank Language class
        print("Created blank 'en' model")

    # create the built-in pipeline components and add them to the pipeline
    # nlp.create_pipe works for built-ins that are registered with spaCy
    if "ner" not in nlp.pipe_names:
        ner = nlp.create_pipe("ner")
        nlp.add_pipe(ner, last=True)
    # otherwise, get it so we can add labels
    else:
        ner = nlp.get_pipe("ner")
    train_data_list = []
    for i, records in enumerate(train_data):
        data = records.get("data")
        text = data["text"]
        for i, annotation in enumerate(records.get("annotations")):
            for result in annotation.get("result"):
                value = result.get("value")
                label = value["labels"][0]
                start = value["start"]
                end = value["end"]
                train_data_list.append((text, {"entities": [(start, end, label)]}))

    # slicing the data
    train_data_list = train_data_list[:10]

    # add labels
    for _, annotations in train_data_list:
        for ent in annotations.get("entities"):
            ner.add_label(ent[2])

    # for records in train_data:
    #     for annotation in records.get("annotations"):
    #         for result in annotation.get("result"):
    #             value = result.get("value")
    #             labels = value.get("labels")
    #             for label in labels:
    #                 ner.add_label(label)

    # Get the transformer component
    transformer = nlp.get_pipe("transformer")

    # get names of other pipes to disable them during training
    pipe_exceptions = ["ner", "transformer", "trf_tok2vec"]
    other_pipes = [pipe for pipe in nlp.pipe_names if pipe not in pipe_exceptions]
    # only train NER
    with nlp.disable_pipes(*other_pipes), warnings.catch_warnings():
        # show warnings for misaligned entity spans once
        warnings.filterwarnings("once", category=UserWarning, module='spacy')

        # Reset but don't initialize transformer weights
        optimizer = nlp.resume_training()

        # reset and initialize the weights randomly – but only if we're
        # training a new model
        if model is None:
            nlp.begin_training()
        for itn in range(n_iter):
            random.shuffle(train_data_list)
            # random.shuffle(train_data)
            losses = {}
            # batch up the examples using spaCy's minibatch
            batches = minibatch(train_data_list, size=compounding(4.0, 32.0, 1.001))
            for batch in batches:
                examples = []
                for text, annotations in batch:
                    doc = nlp.make_doc(text)
                    example = Example.from_dict(doc, annotations)
                    examples.append(example)
                # Update the model
                nlp.update(
                    examples,
                    drop=0.2,  # Lower dropout
                    losses=losses,
                    sgd=optimizer,
                )
                # # texts, annotations = zip(*batch)
                # nlp.update(
                #     texts,  # batch of texts
                #     annotations,  # batch of annotations
                #     drop=0.5,  # dropout - make it harder to memorise data
                #     losses=losses,
                # )
            print("Losses", losses)

    # test the trained model
    for text, _ in train_data_list:
        doc = nlp(text)
        print("Entities", [(ent.text, ent.label_) for ent in doc.ents])
        print("Tokens", [(t.text, t.ent_type_, t.ent_iob) for t in doc])

    # save model to output directory
    if output_dir is not None:
        output_dir = Path(output_dir)
        if not output_dir.exists():
            output_dir.mkdir()
        nlp.to_disk(output_dir)
        print("Saved model to", output_dir)

        # test the saved model
        print("Loading from", output_dir)
        nlp2 = spacy.load(output_dir)
        for text, _ in train_data_list:
            doc = nlp2(text)
            print("Entities", [(ent.text, ent.label_) for ent in doc.ents])
            print("Tokens", [(t.text, t.ent_type_, t.ent_iob) for t in doc])


if __name__ == "__main__":
    plac.call(main)
