import java.util.Scanner;

public class PalindromeNumber {
    public static boolean isPalnum(int x) {
        int orig = x, rev = 0;
        while (x > 0) {
            rev = rev * 10 + (x % 10);
            x /= 10;
        }
        return rev == orig;
    }

    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in);
        int n = scanner.nextInt();
        for (int i = 0; i < n; ++i) {
            int v = scanner.nextInt();
            System.out.println(v + " -> " + (isPalnum(v) ? "PALINDROME" : "NOT"));
        }
        scanner.close();
    }
}