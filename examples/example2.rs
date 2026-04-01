/// Counts the number of words in a string.
/// Words are separated by whitespace. Punctuation attached to words is ignored.
pub fn word_count(s: &str) -> usize {
    s.split_whitespace()
        .filter(|w| w.chars().any(|c| c.is_alphabetic()))
        .count()
}

/// Returns true if the string is a palindrome.
/// Comparison is case-insensitive and ignores non-alphanumeric characters.
pub fn is_palindrome(s: &str) -> bool {
    let cleaned: Vec<char> = s
        .chars()
        .filter(|c| c.is_alphanumeric())
        .map(|c| c.to_ascii_lowercase())
        .collect();
    let reversed: Vec<char> = cleaned.iter().rev().cloned().collect();
    cleaned == reversed
}

/// Truncates a string to at most `max_chars` characters.
/// If truncated, appends "..." without exceeding the character limit.
pub fn truncate(s: &str, max_chars: usize) -> String {
    if s.chars().count() <= max_chars {
        return s.to_string();
    }
    let ellipsis = "...";
    let ellipsis_len = ellipsis.chars().count();
    let take = max_chars.saturating_sub(ellipsis_len);
    let truncated: String = s.chars().take(take).collect();
    format!("{}{}", truncated, ellipsis)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_word_count() {
        assert_eq!(word_count("hello world"), 2);
        assert_eq!(word_count("  spaces  "), 1);
        assert_eq!(word_count(""), 0);
        assert_eq!(word_count("one, two, three."), 3); // punctuation ignored
        assert_eq!(word_count("--- !!!"), 0);          // no alphabetic words
    }

    #[test]
    fn test_is_palindrome() {
        assert!(is_palindrome("racecar"));
        assert!(is_palindrome("Racecar")); // now case-insensitive
        assert!(is_palindrome("A man a plan a canal Panama"));
        assert!(!is_palindrome("hello"));
    }

    #[test]
    fn test_truncate() {
        assert_eq!(truncate("hello world", 5), "he...");
        assert_eq!(truncate("hi", 10), "hi");
        assert_eq!(truncate("hello world", 11), "hello world"); // exact fit, no ellipsis
        assert_eq!(truncate("abcdefgh", 6), "abc...");
    }
}
