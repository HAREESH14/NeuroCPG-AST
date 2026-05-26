import java.util.Scanner;

public class PalindromeCheck {
    public static int isPalindrome(char[] s) {
        int len = 0;
        while (len < s.length && s[len] != '\0') len++;
        int i = 0, j = len-1;
        while (i < j) {
            if (s[i] != s[j]) return 0;
            i++; j--;
        }
        return 1;
    }

    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in);
        int n = scanner.nextInt();
        scanner.nextLine();
        for (int i = 0; i < n; ++i) {
            String input = scanner.nextLine();
            char[] s = new char[100];
            input.getChars(0, input.length(), s, 0);
            for (int k = 0; k < input.length(); k++) System.out.print(s[k]);
            System.out.println(" -> " + (isPalindrome(s) == 1 ? "PALINDROME" : "NOT"));
        }
        scanner.close();
    }
}