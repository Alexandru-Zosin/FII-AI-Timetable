import pandas as pd
from collections import defaultdict
import sys
import nltk
from nltk.corpus import wordnet, stopwords # accessing corpora (collection of written texts)
from nltk.tokenize import word_tokenize, sent_tokenize # text->indiv word & text->sentences tokenizer
from nltk.tag import pos_tag # identification of words
from string import punctuation # globally available constant (pre-defined string)
import random

# required NLTK resources
nltk.download('punkt_tab') # tokenizer model for splitting into word & sentences
nltk.download('averaged_perceptron_tagger_eng') # identifies nouns, verbs, adjectives
nltk.download('wordnet') # large database of english that organizes words into synsets
nltk.download('stopwords') # common words (language-specific words) not useful in NLP tasks (e.g.: are, is...) 
                           # => irrelevant words do not appear as keywords/replacements
"""a naive Bayes classifier for language detection 
 (https://zehengl.github.io/using-naive-bayes-model-for-language-detection/)
 words cannot be used as features, because the training data would have to be really extensive, instead
 we use 3-grams of words (e.g. for hello: "hel, llo, ...")
 P(Y = y | X) = P(X | Y) * P(Y) / P(X), where:
   Y is the language
   X are ALL the 3grams in our text (and we assume cond. indep. between them)
   P(Y = y | X) the probability that the text belongs to language y given the input(3gram) X
    ---------------------------------------------------
   P(X | Y = y) the probability of observing X given the language y
    ~count of X in texts of language y / total 3grams in language of y~
   P(Y = y) the probability of language y (based on how often it appears in the training data)
    ~no of y texts / total no of texts~ !!! equal on our training data
   P(X) the probability of observing X across all langauges
    ~not used in practice, as we need argmax~
and the program precomputes P(X | Y = y) for all 3grams and languages during training
(build_language_models() below), then we use them to compute P(Y = y | X) in detect_language()
"""
def create_3grams(text):
    # converts text to lowercase and pads with spaces 
    # => model is case-insensitive and we obtain meaningful features
    # e.g. for "hi": instead of [], we get [" hi", "hi "]
    text = ' ' + text.lower() + ' '
    # generates 3-grams(slices) from text
    return [text[i:i+3] for i in range(len(text)-2)]

def build_language_models(csv_file):
    df = pd.read_csv(csv_file) # loads the file into a dataframe
    
    # initializing language models and totals with default values for missing keys
    # trigram counts for each language
    language_models = defaultdict(lambda: defaultdict(int))  # another deefaultdict(int)
    # total number of trigrams for each language
    language_totals = defaultdict(int) # 0
    
    # processing each text entry
    for _, row in df.iterrows(): # for each text and language
        text = str(row[0])
        language = str(row[1])
        
        # generating 3-grams for text
        trigrams = create_3grams(text)
        
        # counting trigrams for this language
        for trigram in trigrams:
            language_models[language][trigram] += 1
            language_totals[language] += 1
    
    # converting counts to probabilities
    for language in language_models:
        total = language_totals[language]
        for trigram in language_models[language]:
            language_models[language][trigram] /= total
        # we get P("***" | English), P("^*^" | Portuguese), ...

    return dict(language_models)
    """
    {
        "English": {
            "***": prob. value,
            "^*^": prob. value,
            ...
        },
        ...
    }
    """

def detect_language(text, language_models): #argmax for Y (which language)
    # generating 3-grams for input text
    trigrams = create_3grams(text)
    
    # calculating average probability for each language
    scores = defaultdict(float)

    for language in language_models:
        total_prob = 0
        count = 0
        for trigram in trigrams:
            if trigram in language_models[language]:
                total_prob += language_models[language][trigram]
                count += 1
        
        if count > 0:
            scores[language] = total_prob / count # avg. prob. for P(X | Y = y)
        # avoids favorization of longer text (having many/multiple 3grams) that would obviously
        # have a higher cumulative probability, EVEN THOUGH the matches could be bad/low quality

    # we use addition instead of conventional multiplication to avoid underflow
    # e.g.: [0.01, 0.02, ...] - probabilities that, if multiplied, would result in a close to 0 value
    # because it's still relevant: NB just ranks classes, so the exact calculation is not that important

    # returning language with highest probability (argmax)
    if scores:
        return max(scores.items(), key=lambda x: x[1])[0] # comprs. on avg.prob(x[1]) to extract lng.([0])
    return "Unknown"
    

def get_stylometric_info(text):
    # tokenize text
    words = word_tokenize(text)
    sentences = sent_tokenize(text)
    
    word_count = len(words)
    char_count = len(text)
    sentence_count = len(sentences)
    # words frequency
    word_freq = {}
    for word in words:
        if len(word) > 2:
            if word in word_freq:
                word_freq[word] += 1
            else:
                word_freq[word] = 1
    
    # average word length
    avg_word_length = 0
    if word_count > 0:
        avg_word_length = sum(len(word) for word in words) / word_count
    
    print("\nStylometric Information:")
    print(f"Number of words: {word_count}")
    print(f"Number of characters: {char_count}")
    print(f"Number of sentences: {sentence_count}")
    print(f"Average word length: {avg_word_length:.2f}")
    print("\nTop 5 most frequent words:")
    top_5_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:5]
    for word, freq in top_5_words:
        print(f"{word}: {freq}")

def get_wordnet_alternatives(word):
    alternatives = set() #resulting alternatives are unique(no duplicates)
    
    # get synsets (all distinct meanings of a word - be it nouns or verbs or ...)
    synsets = wordnet.synsets(word)
    if not synsets:
        return []
    
    # get synonyms
    for syn in synsets:
        # add synonyms (lemmas within a synset are synonyms - as they share the same definition)
        alternatives.update(lemma.name() for lemma in syn.lemmas())  # we add to the set

        # add hypernyms (broader categories (e.g., "house" → "building")
        hypernyms = syn.hypernyms()
        for hyper in hypernyms:
            alternatives.update(lemma.name() for lemma in hyper.lemmas())
        
        # add antonyms (negated)
        for lemma in syn.lemmas():
            if lemma.antonyms(): # lemma.antonyms() retrieves its antonyms (usually from a diff sysset)
                alternatives.update(f"not {ant.name()}" for ant in lemma.antonyms())
    
    return list(alternatives - {word}) # it's possible the lemmas contained the original word *itself*

def generate_alternative_text(text, detected_language = 'english'):
    words = word_tokenize(text)
    tagged = pos_tag(words)
    
    # number of words to replace (20% of total)
    num_to_replace = max(1, int(len(words) * 0.2))
    
    # get replaceable words (non-stopwords, non-punctuation)
    stop_words = set(stopwords.words(detected_language))
    replaceable = [(i, word) for i, (word, tag) in enumerate(tagged) 
                  if word.lower() not in stop_words 
                  and word not in punctuation]
    
    if not replaceable:
        return text
    
    # randomly select words to replace
    to_replace = random.sample(replaceable, min(num_to_replace, len(replaceable)))
    
    # create new text with replacements
    new_words = words.copy()
    for idx, word in to_replace:
        alternatives = get_wordnet_alternatives(word)
        if alternatives:
            new_words[idx] = random.choice(alternatives)
    
    return ' '.join(new_words)

def extract_keywords(text, detectedLanguage = 'english'):
    # tokenize and tag parts of speech
    words = word_tokenize(text)
    tagged = pos_tag(words) # e.g. [("nature", "noun"), ("is", "verb"), ...]
    
    # get stopwords and punctuation
    stop_words = set(stopwords.words(detectedLanguage))
    stop_words.update(punctuation) #adds punctuation symbols (INDIVIDUALLY) to the sets to be ignored,
                                    #as punctuation string is iterable

    # extract potential keywords (nouns and important verbs)
    keywords = []
    for word, tag in tagged:
        if (word.lower() not in stop_words and 
            len(word) > 2 and 
            tag.startswith(('NN', 'VB', 'JJ'))): #nouns, verbes, adjectives
            keywords.append(word)
    
    # get frequency distribution
    freq_dist = {}
    for word in keywords:
        if word in freq_dist:
            freq_dist[word] += 1
        else:
            freq_dist[word] = 1
    
    # return top keywords
    sorted_keywords = sorted(freq_dist.items(), key=lambda x: x[1], reverse=True)
    return [word for word, freq in sorted_keywords[:5]]

def generate_keyword_sentences(text, keywords):
    sentences = sent_tokenize(text)
    keyword_sentences = {}
    
    # finds sentences containing keywords in the already given text
    for keyword in keywords:
        for sentence in sentences:
            if keyword.lower() in sentence.lower():
                keyword_sentences[keyword] = sentence
                break
    
    return keyword_sentences

def main():
    # koading and build language models
    try:
        language_models = build_language_models('Language_Detection.csv')
    except Exception as e:
        print(f"Error loading language models: {e}")
        return

    print("Enter 'quit' to exit")    
    while True:
        print("\nEnter text to detect language:")
        user_input = input("> ")
        
        if user_input.lower() == 'quit':
            break
        
        if not user_input.strip():
            print("Please enter some text")
            continue
            
        detected_language = detect_language(user_input, language_models)
        print(f"Detected language: {detected_language}")
        
        # add new analysis features
        get_stylometric_info(user_input)
        
        print("\nAlternative text with replacements:")
        alt_text = generate_alternative_text(user_input, detected_language.lower())
        print(alt_text)
        
        print("\nKeywords and their context:")
        keywords = extract_keywords(user_input, detected_language.lower())
        keyword_sentences = generate_keyword_sentences(user_input, keywords)
        for keyword, sentence in keyword_sentences.items():
            print(f"\nKeyword: {keyword}")
            print(f"Context: {sentence}")

if __name__ == "__main__":
    main()