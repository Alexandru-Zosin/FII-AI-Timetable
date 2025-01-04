import pandas as pd
from collections import defaultdict, Counter
import sys
import nltk
from nltk.corpus import wordnet, stopwords
from nltk.tokenize import word_tokenize, sent_tokenize
from nltk.tag import pos_tag
from string import punctuation
import random

# Download required NLTK resources
nltk.download('punkt')
nltk.download('averaged_perceptron_tagger')
nltk.download('wordnet')
nltk.download('stopwords')

# We implemented basically a Naive Bayes classifier for language detection.
def create_3grams(text):
    # Convert text to lowercase and pad with spaces
    text = ' ' + text.lower() + ' '
    # Generate 3-grams from text
    return [text[i:i+3] for i in range(len(text)-2)]

def build_language_models(csv_file):
    # Read CSV file
    df = pd.read_csv(csv_file)
    
    # Initialize language models
    language_models = defaultdict(lambda: defaultdict(int))
    language_totals = defaultdict(int)
    
    # Process each text entry
    for _, row in df.iterrows():
        text = str(row[0])  # First column contains text
        language = str(row[1])  # Second column contains language
        
        # Generate 3-grams for text
        trigrams = create_3grams(text)
        
        # Count trigrams for this language
        for trigram in trigrams:
            language_models[language][trigram] += 1
            language_totals[language] += 1
    
    # Convert counts to probabilities
    for language in language_models:
        total = language_totals[language]
        for trigram in language_models[language]:
            language_models[language][trigram] /= total
    
    return dict(language_models)

def detect_language(text, language_models):
    # Generate 3-grams for input text
    trigrams = create_3grams(text)
    
    # Calculate average probability for each language
    scores = defaultdict(float)
    
    for language in language_models:
        total_prob = 0
        count = 0
        for trigram in trigrams:
            if trigram in language_models[language]:
                total_prob += language_models[language][trigram]
                count += 1
        
        if count > 0:
            scores[language] = total_prob / count
    
    # Return language with highest probability
    if scores:
        return max(scores.items(), key=lambda x: x[1])[0]
    return "Unknown"

def get_stylometric_info(text):
    # Tokenize text
    words = word_tokenize(text)
    sentences = sent_tokenize(text)
    
    # Basic counts
    word_count = len(words)
    char_count = len(text)
    sentence_count = len(sentences)
    
    # Word frequency
    word_freq = Counter(words)
    
    # Average word length
    avg_word_length = sum(len(word) for word in words) / word_count if word_count > 0 else 0
    
    print("\nStylometric Information:")
    print(f"Number of words: {word_count}")
    print(f"Number of characters: {char_count}")
    print(f"Number of sentences: {sentence_count}")
    print(f"Average word length: {avg_word_length:.2f}")
    print("\nTop 5 most frequent words:")
    for word, freq in word_freq.most_common(5):
        print(f"{word}: {freq}")

def get_wordnet_alternatives(word, pos=None):
    alternatives = set()
    
    # Get synsets
    synsets = wordnet.synsets(word)
    if not synsets:
        return []
    
    # Get synonyms
    for syn in synsets:
        # Add synonyms
        alternatives.update(lemma.name() for lemma in syn.lemmas())
        
        # Add hypernyms
        hypernyms = syn.hypernyms()
        for hyper in hypernyms:
            alternatives.update(lemma.name() for lemma in hyper.lemmas())
        
        # Add antonyms (negated)
        for lemma in syn.lemmas():
            if lemma.antonyms():
                alternatives.update(f"not {ant.name()}" for ant in lemma.antonyms())
    
    return list(alternatives - {word})

def generate_alternative_text(text, detected_language = 'english'):
    words = word_tokenize(text)
    tagged = pos_tag(words)
    
    # Number of words to replace (20% of total)
    num_to_replace = max(1, int(len(words) * 0.2))
    
    # Get replaceable words (non-stopwords, non-punctuation)
    stop_words = set(stopwords.words(detected_language))
    replaceable = [(i, word) for i, (word, tag) in enumerate(tagged) 
                  if word.lower() not in stop_words 
                  and word not in punctuation]
    
    if not replaceable:
        return text
    
    # Randomly select words to replace
    to_replace = random.sample(replaceable, min(num_to_replace, len(replaceable)))
    
    # Create new text with replacements
    new_words = words.copy()
    for idx, word in to_replace:
        alternatives = get_wordnet_alternatives(word)
        if alternatives:
            new_words[idx] = random.choice(alternatives)
    
    return ' '.join(new_words)

def extract_keywords(text, detectedLanguage = 'english'):
    # Tokenize and tag parts of speech
    words = word_tokenize(text)
    tagged = pos_tag(words)
    
    # Get stopwords and punctuation
    stop_words = set(stopwords.words(detectedLanguage))
    stop_words.update(punctuation)
    
    # Extract potential keywords (nouns and important verbs)
    keywords = []
    for word, tag in tagged:
        if (word.lower() not in stop_words and 
            len(word) > 2 and 
            tag.startswith(('NN', 'VB', 'JJ'))):
            keywords.append(word)
    
    # Get frequency distribution
    freq_dist = Counter(keywords)
    
    # Return top keywords
    return [word for word, freq in freq_dist.most_common(5)]

def generate_keyword_sentences(text, keywords):
    sentences = sent_tokenize(text)
    keyword_sentences = {}
    
    # Find sentences containing keywords
    for keyword in keywords:
        for sentence in sentences:
            if keyword.lower() in sentence.lower():
                keyword_sentences[keyword] = sentence
                break
    
    return keyword_sentences

def main():
    # Load and build language models
    print("Loading language models...")
    try:
        language_models = build_language_models('Language_Detection.csv')
    except Exception as e:
        print(f"Error loading language models: {e}")
        return

    print("Language detection system ready!")
    print("Enter 'quit' to exit")
    
    while True:
        print("\nEnter text to detect language:")
        user_input = input("> ")
        
        if user_input.lower() == 'quit':
            print("Goodbye!")
            break
        
        if not user_input.strip():
            print("Please enter some text")
            continue
            
        detected_language = detect_language(user_input, language_models)
        print(f"Detected language: {detected_language}")
        
        # Add new analysis features
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