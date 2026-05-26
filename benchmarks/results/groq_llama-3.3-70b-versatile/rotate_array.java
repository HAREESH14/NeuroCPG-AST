import java.util.Scanner;

public class Main {
    public static void rotateRight(int[] a, int n, int k) {
        k %= n;
        int[] b = new int[100];
        for (int i = 0; i < n; ++i) b[(i + k) % n] = a[i];
        for (int i = 0; i < n; ++i) a[i] = b[i];
    }

    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in);
        int[] a = new int[100];
        int n = scanner.nextInt();
        int k = scanner.nextInt();
        if (n > 100) n = 100;
        for (int i = 0; i < n; i++) a[i] = scanner.nextInt();
        rotateRight(a, n, k);
        for (int i = 0; i < n; ++i) System.out.print(a[i] + " ");
        System.out.println();
    }
}