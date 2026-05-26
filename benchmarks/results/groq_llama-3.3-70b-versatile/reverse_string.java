import java.util.Scanner;

public class ReverseString {
    public static void reverse(char[] s) {
        int len = 0;
        while (len < s.length && s[len] != '\0') len++;
        int i = 0, j = len-1;
        while (i < j) {
            char t = s[i]; s[i] = s[j]; s[j] = t;
            i++; j--;
        }
    }

    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in);
        int n = scanner.nextInt();
        scanner.nextLine();
        for (int i = 0; i < n; i++) {
            String input = scanner.nextLine();
            char[] s = input.toCharArray();
            for (int k = 0; k < s.length; k++) System.out.print(s[k]);
            System.out.print(" -> ");
            reverse(s);
            for (int k = 0; k < s.length; k++) System.out.print(s[k]);
            System.out.println();
        }
        scanner.close();
    }
}