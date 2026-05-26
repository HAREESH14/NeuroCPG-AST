import java.util.Scanner;

public class GCD {
    public static int gcd(int a, int b) {
        if (b == 0) return a >= 0 ? a : -a;
        return gcd(b, a % b);
    }

    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in);
        int a = scanner.nextInt();
        int b = scanner.nextInt();
        System.out.println("GCD of " + a + " and " + b + " is " + gcd(a, b));
    }
}