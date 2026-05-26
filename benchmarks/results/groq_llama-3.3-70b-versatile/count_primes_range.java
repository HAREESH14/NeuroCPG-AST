import java.util.Scanner;

public class CountPrimesRange {
    public static int isPrime(int x) {
        if (x < 2) return 0;
        for (int i = 2; i * i <= x; ++i) if (x % i == 0) return 0;
        return 1;
    }

    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in);
        int n = scanner.nextInt();
        int count = 0;
        for (int i = 2; i <= n; ++i) if (isPrime(i)) ++count;
        System.out.println("Primes up to " + n + ": " + count);
    }
}