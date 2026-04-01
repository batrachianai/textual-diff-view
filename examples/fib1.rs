/// Calculates the nth Fibonacci number (0-indexed).
///
/// # Examples
/// ```
/// assert_eq!(fibonacci(0), 0);
/// assert_eq!(fibonacci(1), 1);
/// assert_eq!(fibonacci(10), 55);
/// ```
pub fn fibonacci(n: u64) -> u64 {
    if n == 0 {
        return 0;
    }

    let (mut a, mut b) = (1u64, 1u64);

    for _ in 0..n {
        (a, b) = (b, a + b);
    }

    a
}
