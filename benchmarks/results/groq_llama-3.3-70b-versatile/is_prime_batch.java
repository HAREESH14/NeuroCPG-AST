import java.util.Scanner;

public class IsPrimeBatch {
    public static int isPrime(int n) {
        if (n <= 1) return 0;
        if (n <= 3) return 1;
        if (n % 2 == 0) return 0;
        int r = (int)Math.sqrt(n);
        for (int i = 3; i <= r; i += 2) if (n % i == 0) return 0;
        return 1;
    }

    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in);
        int n = scanner.nextInt();
        for (int i = 0; i < n; ++i) {
            int v = scanner.nextInt();
            System.out.println(v + " -> " + (isPrime(v) == 1 ? "PRIME" : "COMPOSITE"));
        }
        scanner.close();
    }
}