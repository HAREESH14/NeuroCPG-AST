import java.util.Scanner;

public class PrimeSieve {
    public static void sieve(int n) {
        int[] isPrime = new int[1000];
        for (int i = 0; i <= n; ++i) isPrime[i] = 1;
        isPrime[0] = isPrime[1] = 0;
        for (int p = 2; p * p <= n; ++p) {
            if (isPrime[p]) {
                for (int multiple = p * p; multiple <= n; multiple += p) isPrime[multiple] = 0;
            }
        }
        for (int i = 2; i <= n; ++i) if (isPrime[i]) System.out.print(i + " ");
        System.out.println();
    }

    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in);
        int n = scanner.nextInt();
        if (n > 999) n = 999;
        sieve(n);
    }
}