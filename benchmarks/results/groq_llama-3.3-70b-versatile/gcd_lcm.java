import java.util.Scanner;

public class GCDLCM {
    public static int gcd(int a, int b) {
        if (a < 0) a = -a; if (b < 0) b = -b;
        while (b != 0) {
            int t = b;
            b = a % b;
            a = t;
        }
        return a;
    }

    public static int lcm(int a, int b) {
        int g = gcd(a, b);
        if (g == 0) return 0;
        return (a / g) * b;
    }

    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in);
        int x = scanner.nextInt();
        int y = scanner.nextInt();
        System.out.println("Numbers: " + x + ", " + y);
        System.out.println("GCD: " + gcd(x, y));
        System.out.println("LCM: " + lcm(x, y));
    }
}