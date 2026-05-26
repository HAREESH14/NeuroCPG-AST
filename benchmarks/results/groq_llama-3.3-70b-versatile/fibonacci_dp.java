import java.util.Scanner;

public class FibonacciDP {
    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in);
        int n = scanner.nextInt();
        if (n > 99) n = 99;
        long[] f = new long[100];
        f[0] = 0; f[1] = 1;
        for (int i = 2; i <= n; ++i) f[i] = f[i-1] + f[i-2];
        for (int i = 0; i <= n; ++i) System.out.println(i + ": " + f[i]);
    }
}