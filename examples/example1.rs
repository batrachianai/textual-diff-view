/// Counts the number of words in a string.
/// Words are separated by whitespace.
pub fn word_count(s: &str) -> usize {
    s.split_whitespace().count()
}

/// Returns true if the string is a palindrome.
/// Comparison is case-sensitive.
pub fn is_palindrome(s: &str) -> bool {
    let chars: Vec<char> = s.chars().collect();
    let reversed: Vec<char> = chars.iter().rev().cloned().collect();
    chars == reversed
}

/// Truncates a string to at most `max_chars` characters.
/// No ellipsis is added.
pub fn truncate(s: &str, max_chars: usize) -> &str {
    match s.char_indices().nth(max_chars) {
        Some((idx, _)) => &s[..idx],
        None => s,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_word_count() {
        assert_eq!(word_count("hello world"), 2);
        assert_eq!(word_count("  spaces  "), 1);
        assert_eq!(word_count(""), 0);
    }

    #[test]
    fn test_is_palindrome() {
        assert!(is_palindrome("racecar"));
        assert!(!is_palindrome("Racecar")); // case-sensitive
        assert!(!is_palindrome("hello"));
    }

    #[test]
    fn test_truncate() {
        assert_eq!(truncate("hello world", 5), "hello");
        assert_eq!(truncate("hi", 10), "hi");
    }
}
