import java.util.Scanner;

public class CumulativeSum {
    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in);
        int n = scanner.nextInt();
        if (n > 100) n = 100;
        int[] a = new int[n];
        int[] pref = new int[n];
        for (int i = 0; i < n; ++i) {
            a[i] = scanner.nextInt();
        }
        pref[0] = a[0];
        for (int i = 1; i < n; ++i) pref[i] = pref[i-1] + a[i];
        for (int i = 0; i < n; ++i) System.out.print(pref[i] + " ");
        System.out.println();
    }
}