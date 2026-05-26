import java.util.Scanner;

public class SieveOfEratosthenes {
    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in);
        int N = scanner.nextInt();
        if (N < 2 || N > 1999) return;
        int[] isPrime = new int[N + 1];
        for (int i = 0; i <= N; i++) isPrime[i] = 1;
        isPrime[0] = isPrime[1] = 0;
        for (int p = 2; p * p <= N; ++p) {
            if (isPrime[p]) {
                for (int k = p * p; k <= N; k += p) isPrime[k] = 0;
            }
        }
        System.out.println("Primes up to " + N + ":");
        for (int i = 2; i <= N; ++i) if (isPrime[i]) System.out.print(i + " ");
        System.out.println();
    }
}